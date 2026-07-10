// YT Music 浏览器内 InnerTube 操作(凭据过期时的推送方案)。
//
// 用法:在已登录 music.youtube.com 的标签页里(Claude in Chrome 的 javascript_tool)
// 整段执行本文件建立 window.__yt,然后:
//   await __yt.rebuild('PLxxxx', ['vid1', 'vid2', ...])   // 清空重建,自动校验顺序
//   await __yt.fetchPlaylist('PLxxxx')                     // 读取(含翻页)
//
// 已知行为(2026-07 实测):
// - 写后读有几秒延迟,校验前要等待(verify 内置 6s)。
// - 个别歌单添加批次落在顶部而非底部,rebuild 校验失败且数量正确时会自动
//   用逆序批次重来一遍。
// - YT 可能把提交的 videoId 替换成等价规范视频(常见于原视频失效),
//   校验会报 firstDiff;用 get_song 确认是同曲后回写本地即可,不算错误。
// - 批量写入偶发 409 ABORTED,重试即可(addAll 内置 4 次退避重试)。
// - 大数组嵌入后先核对长度与校验和再执行(防手抄错):
//   本地: sum(ord(c) for c in json.dumps(list, separators=(',',':')))

window.__yt = window.__yt || {};

__yt.sapisidHash = async function () {
  const get = n => document.cookie.split('; ').find(c => c.startsWith(n + '='))?.slice(n.length + 1);
  const sapisid = get('SAPISID') || get('__Secure-3PAPISID');
  const ts = Math.floor(Date.now() / 1000);
  const buf = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(`${ts} ${sapisid} https://music.youtube.com`));
  const hex = [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
  return `SAPISIDHASH ${ts}_${hex}`;
};

__yt.call = async function (endpoint, body) {
  const resp = await fetch(`https://music.youtube.com/youtubei/v1/${endpoint}?prettyPrint=false`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': await __yt.sapisidHash(),
      'X-Goog-AuthUser': String(ytcfg.get('SESSION_INDEX') ?? '0'),
      'X-Origin': 'https://music.youtube.com',
    },
    body: JSON.stringify({ context: ytcfg.get('INNERTUBE_CONTEXT'), ...body }),
  });
  return { status: resp.status, data: await resp.json() };
};

__yt.collectItems = function (obj, out) {
  if (!obj || typeof obj !== 'object') return;
  if (obj.playlistItemData && obj.playlistItemData.videoId) out.push({
    videoId: obj.playlistItemData.videoId,
    setVideoId: obj.playlistItemData.playlistSetVideoId,
  });
  for (const k in obj) __yt.collectItems(obj[k], out);
};

__yt.findContinuation = function (obj) {
  if (!obj || typeof obj !== 'object') return null;
  if (obj.nextContinuationData?.continuation) return obj.nextContinuationData.continuation;
  if (obj.continuationCommand?.token) return obj.continuationCommand.token;
  for (const k in obj) { const t = __yt.findContinuation(obj[k]); if (t) return t; }
  return null;
};

__yt.fetchPlaylist = async function (plid) {
  const r = await __yt.call('browse', { browseId: 'VL' + plid });
  const items = [];
  __yt.collectItems(r.data, items);
  let token = __yt.findContinuation(r.data);
  let pages = 1;
  while (token && pages < 40) {
    const c = await __yt.call('browse', { continuation: token });
    const before = items.length;
    __yt.collectItems(c.data, items);
    token = items.length > before ? __yt.findContinuation(c.data) : null;
    pages++;
  }
  const seen = new Set();
  return items.filter(it => it.setVideoId && !seen.has(it.setVideoId) && seen.add(it.setVideoId));
};

__yt.clearPlaylist = async function (plid) {
  const cur = await __yt.fetchPlaylist(plid);
  for (let i = 0; i < cur.length; i += 50) {
    const batch = cur.slice(i, i + 50);
    for (let a = 0; a < 4; a++) {
      const rr = await __yt.call('browse/edit_playlist', {
        playlistId: plid,
        actions: batch.map(it => ({ action: 'ACTION_REMOVE_VIDEO', setVideoId: it.setVideoId, removedVideoId: it.videoId })),
      });
      if (rr.data.status === 'STATUS_SUCCEEDED') break;
      await new Promise(r => setTimeout(r, 6000));
    }
    await new Promise(r => setTimeout(r, 300));
  }
};

__yt.addAll = async function (plid, list, batchOrderReversed) {
  const batches = [];
  for (let i = 0; i < list.length; i += 50) batches.push(list.slice(i, i + 50));
  if (batchOrderReversed) batches.reverse();
  for (const batch of batches) {
    let ok = false;
    for (let a = 0; a < 4 && !ok; a++) {
      const rr = await __yt.call('browse/edit_playlist', {
        playlistId: plid,
        actions: batch.map(v => ({ action: 'ACTION_ADD_VIDEO', addedVideoId: v })),
      });
      ok = rr.data.status === 'STATUS_SUCCEEDED';
      if (!ok) await new Promise(r => setTimeout(r, 6000));
    }
    if (!ok) throw new Error('add batch failed');
    await new Promise(r => setTimeout(r, 400));
  }
};

__yt.verify = async function (plid, list) {
  await new Promise(r => setTimeout(r, 6000));
  const got = (await __yt.fetchPlaylist(plid)).map(i => i.videoId);
  let firstDiff = -1;
  for (let i = 0; i < list.length; i++) if (got[i] !== list[i]) { firstDiff = i; break; }
  return { count: got.length, expected: list.length, firstDiff, got };
};

// 注意:整个 rebuild 可能超过 CDP 单次调用超时(45s)。歌单大时请分步调用
// clearPlaylist / addAll / verify,而不是直接 rebuild。
__yt.rebuild = async function (plid, list) {
  await __yt.clearPlaylist(plid);
  await new Promise(r => setTimeout(r, 4000));
  await __yt.addAll(plid, list, false);
  let v = await __yt.verify(plid, list);
  let mode = 'normal';
  if (v.firstDiff !== -1 && v.count === list.length) {
    await __yt.clearPlaylist(plid);
    await new Promise(r => setTimeout(r, 4000));
    await __yt.addAll(plid, list, true);
    v = await __yt.verify(plid, list);
    mode = 'batch-reversed';
  }
  return { mode, count: v.count, expected: v.expected, orderOK: v.firstDiff === -1, firstDiff: v.firstDiff };
};
