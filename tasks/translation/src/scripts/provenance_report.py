#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""翻译溯源报告:一个 creator 每篇的执行器/模型/时间/质量指标。

回答"这篇是谁什么时候用什么模型翻的、质量如何"——此前每次都要临时写脚本翻 store,
而 attestation/version/candidate 分散在三个 shard 里,口径容易写歪(例如把 candidate 的
producer 当成发布版本的 producer)。这里固定一套口径:**只看 current ref 指向的那个 version
实际选中的候选**,按 attestation 反查 producer。

用法:
    make provenance CREATOR=9425701 [PROVIDER=pixiv] [FORMAT=table|json|md]
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ..core import document_qa
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core import document_qa


def _shard(ws: Path, kind: str, provider: str, creator: str, sid: str) -> Path:
    return ws / "store" / kind / provider / creator / f"{sid}.jsonl"


def collect(provider: str, creator: str, workspaces_root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for ref_path in sorted(glob.glob(str(workspaces_root / "*" / "store" / "refs" / provider / creator / "*.json"))):
        p = Path(ref_path)
        sid, ws = p.stem, p.parents[4]
        try:
            rev = [json.loads(l) for l in _shard(ws, "document-revision", provider, creator, sid).open(encoding="utf-8")][-1]
            versions = {v["version_id"]: v for v in
                        (json.loads(l) for l in _shard(ws, "document-version", provider, creator, sid).open(encoding="utf-8"))}
            current = json.loads(p.read_text(encoding="utf-8"))["version_id"]
            selections = versions[current]["selections"]
            candidates = {c["candidate_id"]: c for c in
                          (json.loads(l) for l in _shard(ws, "candidate", provider, creator, sid).open(encoding="utf-8"))}
        except (OSError, KeyError, IndexError, json.JSONDecodeError) as exc:
            rows.append({"source_id": sid, "error": f"{type(exc).__name__}: {exc}"})
            continue

        producers: Dict[str, Dict[str, Any]] = {}
        attest = _shard(ws, "attestation", provider, creator, sid)
        published_at = None
        if attest.is_file():
            for line in attest.open(encoding="utf-8"):
                rec = json.loads(line)
                if rec.get("candidate_id"):
                    producers[rec["candidate_id"]] = rec.get("producer") or {}
                    if rec["candidate_id"] in selections.values():
                        published_at = rec.get("created_at") or published_at
        counts = collections.Counter(
            (producers.get(cid, {}).get("type"), producers.get(cid, {}).get("name"),
             producers.get(cid, {}).get("model"))
            for cid in selections.values()
        )
        top = counts.most_common(1)[0][0] if counts else (None, None, None)

        texts = {s["segment_id"]: candidates[selections[s["segment_id"]]]["text"]
                 for s in rev["segments"]
                 if selections.get(s["segment_id"]) in candidates}
        findings = document_qa.audit_document_translations(rev["segments"], texts)
        issue = collections.Counter()
        for f in findings:
            issue[f["code"]] += len(f["indices"]) or 1

        rows.append({
            "source_id": sid,
            "title": rev.get("metadata", {}).get("title") or rev.get("title") or "",
            "segments": len(rev["segments"]),
            "producer_type": top[0], "producer": top[1], "model": top[2],
            "mixed_producers": len(counts) > 1,
            "published_at": published_at,
            "version_id": current,
            "length_ratio": document_qa.translation_length_ratio(rev["segments"], texts),
            "issues": dict(issue),
        })
    rows.sort(key=lambda r: int(r["source_id"]) if r["source_id"].isdigit() else 0)
    return rows


def render_table(rows: List[Dict[str, Any]]) -> str:
    out = [f"{'#':>4} {'source_id':<10} {'执行器':<14} {'模型':<24} {'段':>5} {'比':>5}  {'时间':<10} 问题"]
    for i, r in enumerate(rows, 1):
        if r.get("error"):
            out.append(f"{i:>4} {r['source_id']:<10} ERROR {r['error'][:60]}")
            continue
        ratio = f"{r['length_ratio']:.2f}" if r["length_ratio"] else "  - "
        when = (r["published_at"] or "")[:10]
        issues = ",".join(f"{k}:{v}" for k, v in r["issues"].items()) or "-"
        out.append(f"{i:>4} {r['source_id']:<10} {(r['producer'] or '?'):<14} {(r['model'] or '-'):<24} "
                   f"{r['segments']:>5} {ratio:>5}  {when:<10} {issues}")
    counts = collections.Counter((r.get("producer"), r.get("model")) for r in rows if not r.get("error"))
    out.append("")
    for (name, model), n in counts.most_common():
        out.append(f"  {n:>4} 篇  {name} / {model or '-'}")
    return "\n".join(out)


_HTML_HEAD = """<style>
:root{
  --paper:#EDEFF2; --card:#FFFFFF; --ink:#141A22; --muted:#5A6672; --line:#D3D9E0;
  --accent:#2C5F7C; --accent-soft:#DCE6EC; --alt:#8A5A2B; --alt-soft:#F0E4D6;
  --ok:#2E6B4F; --warn:#9A6B1E; --crit:#9E3B33; --band:#C8D6DE;
}
@media (prefers-color-scheme:dark){
  :root{ --paper:#0E1319; --card:#151C24; --ink:#E6EBF0; --muted:#94A2B0; --line:#26313C;
    --accent:#6FA8C4; --accent-soft:#1B2A34; --alt:#C9945B; --alt-soft:#2A2118;
    --ok:#6DBF97; --warn:#D7A745; --crit:#E0796E; --band:#2B3F4B; }
}
:root[data-theme="dark"]{ --paper:#0E1319; --card:#151C24; --ink:#E6EBF0; --muted:#94A2B0; --line:#26313C;
  --accent:#6FA8C4; --accent-soft:#1B2A34; --alt:#C9945B; --alt-soft:#2A2118;
  --ok:#6DBF97; --warn:#D7A745; --crit:#E0796E; --band:#2B3F4B; }
:root[data-theme="light"]{ --paper:#EDEFF2; --card:#FFFFFF; --ink:#141A22; --muted:#5A6672; --line:#D3D9E0;
  --accent:#2C5F7C; --accent-soft:#DCE6EC; --alt:#8A5A2B; --alt-soft:#F0E4D6;
  --ok:#2E6B4F; --warn:#9A6B1E; --crit:#9E3B33; --band:#C8D6DE; }
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.5;}
.wrap{max-width:1120px;margin:0 auto;padding:48px 24px 96px;}
h1{font-family:Georgia,"Times New Roman",serif;font-weight:600;font-size:34px;margin:0 0 6px;
  letter-spacing:-.01em;text-wrap:balance;}
.sub{color:var(--muted);font-size:15px;margin:0 0 32px;}
.eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);
  margin:0 0 10px;font-weight:600;}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:14px;}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:16px 18px;}
.card .n{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:27px;
  font-variant-numeric:tabular-nums;letter-spacing:-.02em;}
.card .l{color:var(--muted);font-size:12.5px;margin-top:2px;}
.legend{display:flex;flex-wrap:wrap;gap:8px;margin:22px 0 10px;}
.tag{font-size:12px;padding:3px 9px;border-radius:99px;border:1px solid var(--line);
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;}
.tag.a{background:var(--accent-soft);border-color:var(--accent);color:var(--accent);}
.tag.b{background:var(--alt-soft);border-color:var(--alt);color:var(--alt);}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--card);}
table{border-collapse:collapse;width:100%;font-size:13.5px;}
th{position:sticky;top:0;background:var(--card);text-align:left;font-size:11px;letter-spacing:.09em;
  text-transform:uppercase;color:var(--muted);font-weight:600;padding:11px 12px;
  border-bottom:1px solid var(--line);white-space:nowrap;}
td{padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top;}
tr:last-child td{border-bottom:none}
.num,.sid,.seg,.ratio,.date{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-variant-numeric:tabular-nums;white-space:nowrap;}
.num{color:var(--muted);font-size:12px;}
.title{max-width:430px;}
.title span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.meter{display:flex;align-items:center;gap:8px;}
.bar{position:relative;width:74px;height:6px;border-radius:3px;background:var(--line);overflow:hidden;}
.bar i{position:absolute;inset:0 auto 0 0;display:block;border-radius:3px;background:var(--accent);}
.bar b{position:absolute;top:0;bottom:0;background:var(--band);opacity:.55;}
.grp td{background:var(--accent-soft);font-weight:600;font-size:12px;letter-spacing:.05em;
  color:var(--accent);padding:7px 12px;}
.iss{font-size:11.5px;color:var(--warn);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;}
.iss.none{color:var(--muted);opacity:.5}
footer{margin-top:26px;color:var(--muted);font-size:12.5px;}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--accent-soft);
  padding:1px 5px;border-radius:3px;font-size:12.5px;}
</style>"""


def render_html(rows: List[Dict[str, Any]], provider: str, creator: str) -> str:
    import html as _h
    ok = [r for r in rows if not r.get("error")]
    ratios = [r["length_ratio"] for r in ok if r["length_ratio"]]
    prod = collections.Counter((r.get("producer"), r.get("model")) for r in ok)
    issues = sum(sum(r["issues"].values()) for r in ok)
    avg = sum(ratios) / len(ratios) if ratios else 0

    cards = [(len(ok), "已发布篇数"), (f"{avg:.3f}", "平均译文/源文字数比"),
             (f"{min(ratios):.2f}–{max(ratios):.2f}" if ratios else "-", "字数比区间"),
             (sum(r["segments"] for r in ok), "总段数"), (issues, "QA 待核对项")]
    parts = [_HTML_HEAD, '<div class="wrap">',
             f'<p class="eyebrow">翻译溯源 · {_h.escape(provider)}:{_h.escape(creator)}</p>',
             "<h1>每篇译文的来源与时间</h1>",
             '<p class="sub">数据取自 Artifact Store：只统计各篇 current ref 指向的那个版本'
             '实际选中的候选，按 attestation 反查执行器与模型。</p>',
             '<div class="cards">']
    for n, label in cards:
        parts.append(f'<div class="card"><div class="n">{n}</div><div class="l">{label}</div></div>')
    parts.append("</div>")
    parts.append('<div class="legend">')
    for i, ((name, model), n) in enumerate(prod.most_common()):
        parts.append(f'<span class="tag {"a" if i == 0 else "b"}">{_h.escape(name or "?")}'
                     f' · {_h.escape(model or "未记录")} × {n}</span>')
    parts.append("</div>")
    parts.append('<div class="scroll"><table><thead><tr>'
                 "<th>#</th><th>作品 ID</th><th>标题</th><th>执行器 / 模型</th>"
                 "<th>段数</th><th>字数比</th><th>QA</th></tr></thead><tbody>")
    last_day = None
    for i, r in enumerate(ok, 1):
        day = (r["published_at"] or "")[:10]
        if day != last_day:
            parts.append(f'<tr class="grp"><td colspan="7">发布于 {day or "时间未记录"}</td></tr>')
            last_day = day
        ratio = r["length_ratio"] or 0
        # 0.6–0.9 是日译中的健康带;条形按 0–1.2 映射
        fill, band_l, band_w = min(ratio / 1.2, 1) * 100, 0.6 / 1.2 * 100, 0.3 / 1.2 * 100
        iss = ", ".join(f"{k}×{v}" for k, v in r["issues"].items())
        parts.append(
            f'<tr><td class="num">{i}</td><td class="sid">{_h.escape(r["source_id"])}</td>'
            f'<td class="title"><span title="{_h.escape(r["title"])}">{_h.escape(r["title"])}</span></td>'
            f'<td class="sid">{_h.escape(r.get("producer") or "?")} / {_h.escape(r.get("model") or "-")}</td>'
            f'<td class="seg">{r["segments"]}</td>'
            f'<td><div class="meter"><span class="ratio">{ratio:.2f}</span>'
            f'<span class="bar"><b style="left:{band_l:.1f}%;width:{band_w:.1f}%"></b>'
            f'<i style="width:{fill:.1f}%"></i></span></div></td>'
            f'<td class="iss{" none" if not iss else ""}">{_h.escape(iss) or "—"}</td></tr>')
    parts.append("</tbody></table></div>")
    parts.append('<footer>字数比条形上的浅色区间是日译中的健康带 0.6–0.9：低于 0.55 判 '
                 "<code>undertranslation</code>（系统性缩写），高于 1.10 判 <code>overtranslation</code>"
                 "（重复膨胀或混入邻段）。<code>duplicate_translation_distinct_source</code> 多为不同源句"
                 "译出相同短句（如两处纯省略号台词），通常无需处理。<br>"
                 "重新生成：<code>make provenance CREATOR=&lt;id&gt; FORMAT=html</code></footer>")
    parts.append("</div>")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--creator", required=True)
    ap.add_argument("--provider", default="pixiv")
    ap.add_argument("--workspaces-root", type=Path, default=Path("tasks/translation/data/workspaces"))
    ap.add_argument("--format", choices=("table", "json", "html"), default="table")
    args = ap.parse_args()
    rows = collect(args.provider, args.creator, args.workspaces_root)
    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif args.format == "html":
        print(render_html(rows, args.provider, args.creator))
    else:
        print(render_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
