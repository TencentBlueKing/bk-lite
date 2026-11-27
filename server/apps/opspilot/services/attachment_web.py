"""独立 HTML 附件的屏幕版式，样式随文件交付，浏览器离线即可打开。"""

import re
from functools import lru_cache
from pathlib import Path

from apps.opspilot.services.attachment_theme import _cover_notes, _document_front, _escape, _html_body, _html_runs, document_genre

_STYLE = Path(__file__).resolve().parents[1] / "support-files/styles/attachment-web.css"
_HTML_START = re.compile(r"^\s*(?:<!doctype\s+html\b|<!--|<[a-z][\w:-]*(?=[\s/>]))", re.I)


@lru_cache(maxsize=1)
def _stylesheet() -> str:
    return _STYLE.read_text(encoding="utf-8")


def render_web_attachment(content: str, *, title: str, filename: str, genre: str, markdown: bool) -> str:
    from bs4 import BeautifulSoup, Doctype

    if not content.strip():
        return content
    native = not markdown and _HTML_START.match(content)
    if native:
        doc = BeautifulSoup(content, "html.parser")
        # 已有样式、图表或交互的页面由作者控制布局，保持原始源码。
        if doc.select_one('style, [style], link[rel~="stylesheet"], script, svg, canvas, iframe, template'):
            return content
        heading = doc.find("h1")
        title = heading.get_text(" ", strip=True) if heading else (doc.title.get_text(strip=True) if doc.title else title or filename)
        # 原生标题可能是已有锚点或包含内联内容；只为缺标题的文档补标题。
        if not heading:
            heading = doc.new_tag("h1")
            heading.string = title
    else:
        kind = document_genre(genre)
        if not title:
            first_heading = re.match(r"^\s*#\s+([^\n]+)", content)
            title = first_heading[1].strip() if first_heading else filename
        cover, blocks = _document_front(content, title, kind)
        subtitle, meta = _cover_notes(cover, kind)
        header = [f"<h1>{_escape(title)}</h1>"]
        header.extend(f'<p class="intro">{_html_runs(runs)}</p>' for runs in subtitle)
        header.extend(f'<p class="meta">{_html_runs(runs)}</p>' for runs in meta)
        doc = BeautifulSoup(
            '<html lang="zh-CN"><head></head><body><header>' + "".join(header) + "</header>" + _html_body(blocks, kind) + "</body></html>",
            "html.parser",
        )

    if not doc.html:
        root = doc.new_tag("html", lang="zh-CN")
        for child in list(doc.contents):
            if not isinstance(child, Doctype):
                root.append(child.extract())
        doc.append(root)
    if not doc.head:
        doc.html.insert(0, doc.new_tag("head"))
    if not doc.body:
        body = doc.new_tag("body")
        for child in list(doc.html.contents):
            if child is not doc.head:
                body.append(child.extract())
        doc.html.append(body)
    if not doc.title:
        tag = doc.new_tag("title")
        tag.string = title
        doc.head.append(tag)
    if not doc.head.find("meta", charset=True):
        doc.head.insert(0, doc.new_tag("meta", charset="utf-8"))
    if not doc.head.select_one('meta[name="viewport"]'):
        doc.head.append(doc.new_tag("meta", attrs={"name": "viewport", "content": "width=device-width, initial-scale=1"}))
    style = doc.new_tag("style")
    style.string = _stylesheet()
    doc.head.append(style)

    if native:
        # 对已有语义布局只提供基础阅读样式，不移动原页面节点。
        doc.body["class"] = [*doc.body.get("class", []), "native-document"]
        if not heading.parent:
            doc.body.insert(0, heading)
    else:
        header = doc.header.extract()
        article = doc.new_tag("article")
        for child in list(doc.body.contents):
            article.append(child.extract())
        layout = doc.new_tag("main", attrs={"class": "layout"})
        layout.append(article)
        doc.body.extend([header, layout])
        headings = article.find_all(re.compile("^h[1-4]$"))
        top_level = min((h.name for h in headings), default="h2")
        chapters = [h for h in headings if h.name == top_level]
        if len(chapters) > 1:
            nav = doc.new_tag("nav", attrs={"aria-label": "目录"})
            for index, h in enumerate(chapters, 1):
                h["id"] = f"section-{index}"
                link = doc.new_tag("a", href="#" + h["id"])
                link.string = h.get_text(" ", strip=True)
                nav.append(link)
            layout.insert(0, nav)

    for table in doc.find_all("table"):
        region = doc.new_tag("div", attrs={"class": "table-scroll", "tabindex": "0", "role": "region"})
        h = table.find_previous(re.compile("^h[1-6]$"))
        region["aria-label"] = h.get_text(" ", strip=True) if h else title
        table.wrap(region)
    if not any(isinstance(child, Doctype) for child in doc.contents):
        doc.insert(0, Doctype("html"))
    return str(doc)
