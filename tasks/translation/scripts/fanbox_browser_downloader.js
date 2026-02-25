/**
 * Fanbox browser-side downloader.
 *
 * Usage:
 *   1. Open https://<creator>.fanbox.cc/ (log in first).
 *   2. Open DevTools Console (F12), paste this file's contents once to define the helper.
 *   3. (Optional) await fanboxSelectDownloadDirectory() to pick a base directory once.
 *   4. Run: await downloadFanboxPosts({ creatorId: "momizi813" })
 *      - The script reuses the saved directory; use forcePickDirectory or fanboxForgetDownloadDirectory() to change it.
 *      - 默认启用断点续传（会在目录中维护 .fanbox_state.json，并跳过已存在的 postId）
 *        如需重新下载可传 { resume: false } 或删除该状态文件。
 *
 * Files produced:
 *   - {postId}.meta.json  (raw post info)
 *   - {postId}.txt        (YAML front matter + plain-text body)
 *
 * Requires a Chromium-based browser with File System Access API (Chrome/Edge 86+).
 */

const FANBOX_DIR_SYMBOL = "__fanbox_saved_directory__";
let FANBOX_CSRF_TOKEN = null;
let FANBOX_HOST_CREATOR_ID = null;

async function fanboxSelectDownloadDirectory() {
  const handle = await window.showDirectoryPicker();
  window[FANBOX_DIR_SYMBOL] = handle;
  console.log("[fanbox] 已保存下载目录句柄，可重复使用。");
  return handle;
}

function fanboxForgetDownloadDirectory() {
  delete window[FANBOX_DIR_SYMBOL];
  console.log("[fanbox] 已清除保存的目录句柄。");
}

async function ensureDownloadDirectory(forcePick = false) {
  if (!forcePick && window[FANBOX_DIR_SYMBOL]) {
    return window[FANBOX_DIR_SYMBOL];
  }
  return fanboxSelectDownloadDirectory();
}

function detectCreatorIdFromLocation() {
  const hostMatch = location.hostname.match(/^([^.]+)\.fanbox\.cc$/);
  if (hostMatch && hostMatch[1] && hostMatch[1] !== "www") {
    return hostMatch[1];
  }
  const pathMatch = location.pathname.match(/@([^/]+)/);
  if (pathMatch && pathMatch[1]) {
    return pathMatch[1];
  }
  return FANBOX_HOST_CREATOR_ID || null;
}

async function downloadFanboxPosts(options) {
  const {
    creatorId,
    limit = 50,
    delayMs = 500,
    detailDelayMs = 1500,
    includePaid = true,
    forcePickDirectory = false,
    directoryHandle: explicitHandle = null,
    maxRetries = 5,
    resume = true,
    retryDelayMs,
  } = options || {};

  const detectedCreatorId = creatorId || detectCreatorIdFromLocation();
  if (!detectedCreatorId) {
    throw new Error("creatorId is required (or run on <creator>.fanbox.cc page).");
  }
  const parsedLimit = Number(limit);
  const normalizedLimit = Number.isFinite(parsedLimit)
    ? Math.max(1, Math.min(100, Math.trunc(parsedLimit)))
    : 50;

  const rootHandle =
    explicitHandle || (await ensureDownloadDirectory(forcePickDirectory));
  const creatorDir = await rootHandle.getDirectoryHandle(detectedCreatorId, { create: true });

  const seen = new Set();
  let fetched = 0;
  let skipped = 0;
  let failed = 0;
  const postSummaries = [];

  const authHeaders = await resolveAuthHeaders();
  const retryConfig = {
    maxRetries,
    retryDelayMs: retryDelayMs ?? Math.max(detailDelayMs * 2, delayMs * 2, 1200),
  };

  // 整理现有文件，构建已完成集合
  let existingEntries = [];
  if (resume) {
    existingEntries = await collectExistingPosts(creatorDir);
  }
  const state = resume ? await loadState(creatorDir) : { completed: [] };
  const completedSet = new Set([...(state.completed || []), ...existingEntries]);
  const committedEvery = 5;
  let sinceLastPersist = 0;

  const firstUrl = new URL("https://api.fanbox.cc/post.listCreator");
  firstUrl.searchParams.set("creatorId", detectedCreatorId);
  firstUrl.searchParams.set("limit", String(normalizedLimit));
  firstUrl.searchParams.set("withPinned", "true");

  let nextUrl = firstUrl.toString();

  while (nextUrl) {
    const data = await fetchJson(nextUrl, authHeaders, retryConfig);
    const body = data.body || {};
    const items = body.items || [];
    for (const item of items) {
      if (!includePaid && (item.feeRequired || 0) > 0) {
        continue;
      }
      const id = String(item.id);
      if (seen.has(id)) {
        continue;
      }
      seen.add(id);
      postSummaries.push(item);
    }
    nextUrl = body.nextUrl || null;
    if (nextUrl) {
      nextUrl = ensureAbsolute(nextUrl);
      if (delayMs > 0) {
        await wait(delayMs);
      }
    }
  }

  if (!postSummaries.length) {
    console.warn("[fanbox] post.listCreator 未返回内容，尝试 post.paginateCreator 回退。");
    const urls = await fetchPaginateUrls(detectedCreatorId, authHeaders, retryConfig);
    for (const pageUrl of urls) {
      const pageData = await fetchJson(pageUrl, authHeaders, retryConfig);
      const items = pageData.body || [];
      for (const item of items) {
        if (!includePaid && (item.feeRequired || 0) > 0) {
          continue;
        }
        const id = String(item.id);
        if (seen.has(id)) {
          continue;
        }
        seen.add(id);
        postSummaries.push(item);
      }
      if (delayMs > 0) {
        await wait(delayMs);
      }
    }
  }

  for (const summary of postSummaries) {
    const postId = String(summary.id);
    if (resume) {
      if (completedSet.has(postId)) {
        console.log(`[fanbox] skip completed ${postId}`);
        skipped += 1;
        continue;
      }
    }
    console.log(`[fanbox] fetching ${postId} - ${summary.title || ""}`);
    let detail;
    try {
      detail = await fetchPostDetail(postId, authHeaders, retryConfig);
    } catch (error) {
      console.error(`[fanbox] 获取详情失败，跳过 ${postId}:`, error);
      failed += 1;
      if (resume) {
        await saveState(creatorDir, completedSet);
      }
      continue;
    }
    if (!detail) {
      console.warn(`[fanbox] empty detail for ${postId}`);
      failed += 1;
      continue;
    }
    const { bodyType, bodyText } = extractBody(detail);
    const yaml = buildYamlFrontmatter(detail, bodyType, detectedCreatorId);
    await writeFile(creatorDir, `${postId}.meta.json`, JSON.stringify(detail, null, 2));
    await writeFile(creatorDir, `${postId}.txt`, `${yaml}${bodyText}\n`);
    fetched += 1;
    if (resume) {
      completedSet.add(postId);
      sinceLastPersist += 1;
      if (sinceLastPersist >= committedEvery) {
        await saveState(creatorDir, completedSet);
        sinceLastPersist = 0;
      }
    }
    if (detailDelayMs > 0) {
      await wait(detailDelayMs);
    }
  }

  if (resume) {
    await saveState(creatorDir, completedSet);
  }

  const summary = {
    creatorId: detectedCreatorId,
    fetched,
    skipped,
    failed,
    totalCandidates: postSummaries.length,
    outputDir: creatorDir,
  };
  console.log(
    `[fanbox] 完成，新增 ${fetched}，跳过 ${skipped}，失败 ${failed}。目标目录：`,
    creatorDir
  );
  return summary;
}

async function fetchJson(url, headers, retryOptions = {}) {
  const {
    maxRetries = 3,
    retryDelayMs = 1000,
    retryOn = [429, 500, 502, 503, 504],
  } = retryOptions;

  let attempt = 0;
  while (true) {
    attempt += 1;
    try {
      const resp = await fetch(url, {
        credentials: "include",
        headers,
        mode: "cors",
      });
      if (!resp.ok) {
        const status = resp.status ?? 0;
        const snippet = await resp.text().catch(() => "");
        if (retryOn.includes(status) && attempt <= maxRetries) {
          const waitMs = retryDelayMs * attempt;
          console.warn(`[fanbox] HTTP ${status}，将在 ${waitMs}ms 后重试：${url}`);
          await wait(waitMs);
          continue;
        }
        throw new Error(`HTTP ${status} for ${url} - ${snippet.slice(0, 200)}`);
      }
      return await resp.json();
    } catch (error) {
      if (attempt > maxRetries) {
        throw error;
      }
      const waitMs = retryDelayMs * attempt;
      console.warn(`[fanbox] 请求失败，将在 ${waitMs}ms 后重试：${url}`);
      await wait(waitMs);
    }
  }
}

async function fetchPostDetail(postId, headers, retryOptions) {
  const url = `https://api.fanbox.cc/post.info?postId=${postId}`;
  const data = await fetchJson(url, headers, retryOptions);
  return data.body || null;
}

function ensureAbsolute(url) {
  if (!url) {
    return null;
  }
  if (url.startsWith("http")) {
    return url;
  }
  if (url.startsWith("//")) {
    return `https:${url}`;
  }
  return `https://api.fanbox.cc${url.startsWith("/") ? url : `/${url}`}`;
}

async function writeFile(dirHandle, filename, contents) {
  const fileHandle = await dirHandle.getFileHandle(filename, { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(contents);
  await writable.close();
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function sanitize(text) {
  return (text || "").replace(/\r\n?/g, "\n");
}

function buildYamlFrontmatter(detail, bodyType, creatorId) {
  const creator = detail.creator || {};
  const tags = Array.isArray(detail.tags) ? detail.tags : [];
  const tagList = tags.map((tag) => String(tag).trim()).filter(Boolean);
  const lines = [
    "---",
    `post_id: ${detail.id}`,
    `title: ${yamlEscape(detail.title)}`,
    `excerpt: ${yamlEscape(detail.excerpt || detail.lead || "")}`,
    "creator:",
    `  id: ${yamlEscape(creator.creatorId || creatorId || detail.creatorId)}`,
    `  name: ${yamlEscape(creator.name || "")}`,
    `fee_required: ${detail.feeRequired ?? 0}`,
    `is_restricted: ${detail.isRestricted ?? false}`,
    `published_at: ${yamlEscape(detail.publishedDatetime || detail.publishedAt || "")}`,
    `updated_at: ${yamlEscape(detail.updatedDatetime || detail.updatedAt || "")}`,
    `body_type: ${yamlEscape(bodyType)}`,
    `tags: [${tagList.join(", ")}]`,
    `source_url: https://${creatorId}.fanbox.cc/posts/${detail.id}`,
    "lang: ja",
    "---",
    "",
  ];
  return lines.join("\n");
}

function yamlEscape(value) {
  if (value === null || value === undefined) {
    return "";
  }
  const text = String(value).trim();
  return text.replace(/\n/g, " ");
}

async function resolveAuthHeaders() {
  if (!FANBOX_CSRF_TOKEN) {
    const meta = document.querySelector('meta[name="metadata"]');
    if (meta && meta.content) {
      try {
        const parsed = JSON.parse(meta.content);
        FANBOX_CSRF_TOKEN = parsed?.csrfToken || null;
        FANBOX_HOST_CREATOR_ID = parsed?.urlContext?.host?.creatorId || null;
      } catch (err) {
        console.warn("[fanbox] 解析 csrfToken 失败", err);
      }
    }
  }
  const headers = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
  };
  if (FANBOX_CSRF_TOKEN) {
    headers["X-CSRF-Token"] = FANBOX_CSRF_TOKEN;
  }
  return headers;
}

async function fetchPaginateUrls(creatorId, headers, retryOptions) {
  try {
    const data = await fetchJson(
      `https://api.fanbox.cc/post.paginateCreator?creatorId=${creatorId}`,
      headers,
      retryOptions
    );
    return (data.body || []).map((url) => ensureAbsolute(url)).filter(Boolean);
  } catch (err) {
    console.warn("[fanbox] post.paginateCreator 请求失败", err);
    return [];
  }
}

async function loadState(dirHandle) {
  try {
    const fileHandle = await dirHandle.getFileHandle(".fanbox_state.json", { create: false });
    const file = await fileHandle.getFile();
    const text = await file.text();
    const parsed = JSON.parse(text);
    const completed = Array.isArray(parsed?.completed)
      ? parsed.completed.map((id) => String(id))
      : [];
    return { completed };
  } catch (err) {
    return { completed: [] };
  }
}

async function saveState(dirHandle, completedSet) {
  try {
    const fileHandle = await dirHandle.getFileHandle(".fanbox_state.json", { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(JSON.stringify({ completed: Array.from(completedSet) }, null, 2));
    await writable.close();
  } catch (err) {
    console.warn("[fanbox] 保存进度失败", err);
  }
}

async function fileExists(dirHandle, filename) {
  try {
    await dirHandle.getFileHandle(filename, { create: false });
    return true;
  } catch (err) {
    return false;
  }
}

async function collectExistingPosts(dirHandle) {
  const files = [];
  for await (const entry of dirHandle.values()) {
    if (entry.kind === "file" && entry.name.endsWith(".txt")) {
      const match = entry.name.match(/^(\d+)\.txt$/);
      if (match) {
        const postId = match[1];
        const metaExists = await fileExists(dirHandle, `${postId}.meta.json`);
        if (metaExists) {
          files.push(postId);
        }
      }
    }
  }
  if (files.length) {
    console.log(`[fanbox] 检测到本地已有 ${files.length} 篇文章，将跳过重复下载。`);
  }
  return files;
}

function extractBody(detail) {
  const body = detail.body || {};
  const bodyType = body.type || detail.type || "unknown";
  let text = "";

  if (bodyType === "article") {
    text = extractArticle(body);
  } else if (bodyType === "html") {
    text = htmlToText(body.html || "");
  } else if (bodyType === "text" || bodyType === "blog") {
    text = sanitize(body.text || "");
  } else if (bodyType === "image") {
    const images = body.images || [];
    text = images.map((img) => `[image] ${img.caption || img.id || ""}`.trim()).join("\n");
  } else if (bodyType === "file") {
    const files = body.files || [];
    text = files.map((file) => `[file] ${file.name || file.id || ""}`.trim()).join("\n");
  } else {
    if (body.html) {
      text = htmlToText(body.html);
    } else if (body.text) {
      text = sanitize(body.text);
    } else {
      text = JSON.stringify(body, null, 2);
    }
  }

  return { bodyType, bodyText: text.trim() };
}

function extractArticle(body) {
  const blocks = body.blocks || [];
  const lines = [];

  for (const block of blocks) {
    const type = block.type;
    if (type === "p" || type === "text") {
      const txt = block.text || "";
      if (txt.trim()) {
        lines.push(txt.trim());
      }
    } else if (type === "header" || type === "heading") {
      const txt = block.text || "";
      if (txt.trim()) {
        lines.push(txt.trim());
      }
    } else if (type === "image") {
      const caption = block.caption || block.text || block.id || block.imageId || "";
      lines.push(`[image] ${caption}`.trim());
    } else if (type === "file") {
      const name = block.name || block.fileId || "attachment";
      lines.push(`[file] ${name}`.trim());
    } else if (type === "embed") {
      const service = block.service || block.serviceProvider || "embed";
      lines.push(`[embed:${service}]`);
    } else if (type === "quote") {
      const txt = block.text || "";
      if (txt.trim()) {
        lines.push(`> ${txt.trim()}`);
      }
    } else if (type === "codeBlock") {
      const txt = block.text || "";
      if (txt) {
        lines.push(txt);
      }
    } else if (block.links && Array.isArray(block.links)) {
      for (const link of block.links) {
        if (link.url) {
          lines.push(link.url);
        }
      }
    } else if (block.text) {
      lines.push(block.text);
    }
  }

  if (!lines.length && body.text) {
    lines.push(body.text);
  }

  return sanitize(lines.join("\n\n"));
}

function htmlToText(html) {
  if (!html) {
    return "";
  }
  const container = document.createElement("div");
  container.innerHTML = html;
  container.querySelectorAll("br").forEach((br) => {
    br.replaceWith("\n");
  });
  container.querySelectorAll("script, style").forEach((node) => node.remove());
  return sanitize(container.textContent || "");
}
