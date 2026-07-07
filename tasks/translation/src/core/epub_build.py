#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简 EPUB3 生成(仅 stdlib):按章列表产出带**显式 TOC** 的电子书。

动机(gh-142 后续):合集 txt 导入微信读书等阅读器时,章节靠行首正则"猜"——正文里的
`第1根`、`第一回`、`8月13日` 都会被误判成章头,真章头反而被挤掉。EPUB 的 spine/nav 是
显式结构,阅读器不再猜。文字书不需要 ebooklib 这类依赖:EPUB 就是一个约定结构的 zip
(mimetype 必须第一个且不压缩 + container.xml + OPF + XHTML)。
"""

from __future__ import annotations

import html
import uuid
import zipfile
from pathlib import Path
from typing import List, Tuple

_CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}">
<head><title>{title}</title></head>
<body>
<h2>{title}</h2>
{body}
</body>
</html>
"""


def _chapter_xhtml(title: str, text: str, lang: str) -> str:
    paras = [f"<p>{html.escape(p)}</p>" for p in text.splitlines() if p.strip()]
    return _XHTML.format(lang=lang, title=html.escape(title), body="\n".join(paras))


def build_epub(
    out_path: Path, book_title: str, author: str,
    chapters: List[Tuple[str, str]], *, language: str = "zh",
) -> Path:
    """chapters = [(章标题, 章正文纯文本), ...] → out_path(.epub)。返回 out_path。"""
    if not chapters:
        raise ValueError("chapters 不能为空")
    out_path = Path(out_path)
    book_id = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, f'{author}/{book_title}')}"
    manifest, spine, nav_lis = [], [], []
    for n, (title, _) in enumerate(chapters, 1):
        manifest.append(
            f'<item id="c{n}" href="c{n}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{n}"/>')
        nav_lis.append(f'<li><a href="c{n}.xhtml">{html.escape(title)}</a></li>')
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">{book_id}</dc:identifier>
    <dc:title>{html.escape(book_title)}</dc:title>
    <dc:creator>{html.escape(author)}</dc:creator>
    <dc:language>{language}</dc:language>
    <meta property="dcterms:modified">1970-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    {chr(10).join(manifest)}
  </manifest>
  <spine>
    {chr(10).join(spine)}
  </spine>
</package>
"""
    nav = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{language}">
<head><title>目录</title></head>
<body>
<nav epub:type="toc"><h1>目录</h1><ol>
{chr(10).join(nav_lis)}
</ol></nav>
</body>
</html>
"""
    with zipfile.ZipFile(out_path, "w") as z:
        # EPUB 规范:mimetype 必须是第一个 entry 且不压缩
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", _CONTAINER_XML, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, zipfile.ZIP_DEFLATED)
        for n, (title, text) in enumerate(chapters, 1):
            z.writestr(f"OEBPS/c{n}.xhtml", _chapter_xhtml(title, text, language),
                       zipfile.ZIP_DEFLATED)
    return out_path
