/**
 * Fanbox 单篇文章导出助手
 *
 * 使用步骤：
 *   1. 登录后打开目标文章页，例如 https://momizi813.fanbox.cc/posts/3819932
 *   2. 打开开发者工具 → Console
 *   3. 粘贴本文件全部内容回车（只需执行一次）
 *   4. 首次运行时可执行：await fanboxSelectDownloadDirectory() 选择一个根目录
 *   5. 随后每次调用：await downloadCurrentFanboxPost()  脚本会自动复用已保存的目录
 *      若想重新指定目录：await downloadCurrentFanboxPost({ forcePickDirectory: true })
 *      或调用 fanboxForgetDownloadDirectory() 清除保存的目录句柄
 *
 * 说明：
 *   - 脚本直接调用官方 API（需已登录且有访问权限）
 *   - 输出格式与 Pixiv 管线保持一致：YAML front matter + 正文纯文本
 *   - 若文章仅开放部分内容，正文会是可见的片段；如完全无正文则落地为 JSON 说明
 */

const FANBOX_DIR_SYMBOL = "__fanbox_saved_directory__";

async function fanboxSelectDownloadDirectory() {
  const handle = await window.showDirectoryPicker();
  window[FANBOX_DIR_SYMBOL] = handle;
  console.log("[fanbox] 已保存下载目录句柄，可在当前标签页重复使用。");
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

async function downloadCurrentFanboxPost(options = {}) {
  const {
    postId: overridePostId,
    creatorId: overrideCreatorId,
    subdir = true,
    delayMs = 0,
    forcePickDirectory = false,
    directoryHandle: explicitHandle = null,
  } = options;

  const detectedPostId =
    overridePostId ||
    (location.pathname.match(/posts\/(\d+)/) || [null, null])[1];
  if (!detectedPostId) {
    throw new Error("无法从当前 URL 解析出 postId，请确认已在文章详情页。");
  }

  let detectedCreatorId = overrideCreatorId || null;
  if (!detectedCreatorId) {
    const hostMatch = location.hostname.match(/^([^.]+)\.fanbox\.cc$/);
    if (hostMatch && hostMatch[1] && hostMatch[1] !== "www") {
      detectedCreatorId = hostMatch[1];
    }
  }
  if (!detectedCreatorId) {
    const pathMatch = location.pathname.match(/@([^/]+)/);
    if (pathMatch && pathMatch[1]) {
      detectedCreatorId = pathMatch[1];
    }
  }
  if (!detectedCreatorId) {
    throw new Error("无法识别 creatorId，请确认页面域名形如 <creator>.fanbox.cc。");
  }

  const rootHandle =
    explicitHandle || (await ensureDownloadDirectory(forcePickDirectory));
  const targetDir = subdir
    ? await rootHandle.getDirectoryHandle(detectedCreatorId, { create: true })
    : rootHandle;

  if (delayMs > 0) {
    await wait(delayMs);
  }

  const detail = await fetchPostDetail(detectedPostId);
  if (!detail) {
    throw new Error("post.info 返回空数据，可能无访问权限或需要重试。");
  }

  const { bodyType, bodyText } = extractBody(detail);
  const yaml = buildYamlFrontmatter(detail, bodyType, detectedCreatorId);

  await writeFile(
    targetDir,
    `${detectedPostId}.meta.json`,
    JSON.stringify(detail, null, 2)
  );
  await writeFile(targetDir, `${detectedPostId}.txt`, `${yaml}${bodyText}\n`);

  console.log(
    `[fanbox] 已导出 ${detectedCreatorId}/${detectedPostId} (${detail.title || ""})`
  );
  return {
    creatorId: detectedCreatorId,
    postId: detectedPostId,
    title: detail.title || "",
    outputDir: targetDir,
  };
}

async function fetchJson(url) {
  const resp = await fetch(url, { credentials: "include" });
  if (!resp.ok) {
    const snippet = await resp.text();
    throw new Error(`HTTP ${resp.status} for ${url} - ${snippet.slice(0, 200)}`);
  }
  return resp.json();
}

async function fetchPostDetail(postId) {
  const url = `https://api.fanbox.cc/post.info?postId=${postId}`;
  const data = await fetchJson(url);
  return data.body || null;
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
    text = images
      .map((img) => `[image] ${img.caption || img.id || ""}`.trim())
      .join("\n");
  } else if (bodyType === "file") {
    const files = body.files || [];
    text = files
      .map((file) => `[file] ${file.name || file.id || ""}`.trim())
      .join("\n");
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

function yamlEscape(value) {
  if (value === null || value === undefined) {
    return "";
  }
  const text = String(value).trim();
  return text.replace(/\n/g, " ");
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
