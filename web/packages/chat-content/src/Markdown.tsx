"use client";
import React, { useEffect, useState } from "react";
import { Image } from "antd";
import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";
import hljs from "highlight.js/lib/common";

const options = {
  html: false,
  highlight: (code: string, language: string) => {
    if (!language || !hljs.getLanguage(language)) return "";
    try {
      return hljs.highlight(code, { language }).value;
    } catch {
      return "";
    }
  },
};
const markdown = new MarkdownIt(options);
const legacyMarkdown = new MarkdownIt({ ...options, html: true });
for (const renderer of [markdown, legacyMarkdown]) {
  renderer.renderer.rules.table_open = () => '<div class="chat-markdown-table"><table>\n';
  renderer.renderer.rules.table_close = () => '</table></div>\n';
}
export const sanitizeChatHtml = (html: string, legacyHtml = true) => {
  // DOMPurify needs a real DOM. Never emit unclean HTML during server rendering.
  if (typeof DOMPurify.sanitize !== 'function') return markdown.utils.escapeHtml(html);
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      "p",
      "br",
      "hr",
      "strong",
      "em",
      "u",
      "s",
      "code",
      "pre",
      "span",
      "div",
      "a",
      "ul",
      "ol",
      "li",
      "h1",
      "h2",
      "h3",
      "h4",
      "h5",
      "h6",
      "blockquote",
      "table",
      "thead",
      "tbody",
      "tr",
      "th",
      "td",
      "img",
      "svg",
      "use",
      "button",
    ],
    ALLOWED_ATTR: [
      ...(legacyHtml ? ["style"] : []),
      "class",
      "href",
      "target",
      "rel",
      "data-ref-number",
      "data-chunk-id",
      "data-knowledge-id",
      "data-chunk-type",
      "data-content",
      "data-suggestion",
      "data-expanded",
      "data-tool-id",
      "data-has-detail",
      "src",
      "alt",
      "width",
      "height",
      "aria-hidden",
    ],
    ALLOW_DATA_ATTR: false,
  });
};
export const renderChatMarkdown = (content: string, legacyHtml = false) =>
  sanitizeChatHtml(
    (legacyHtml ? legacyMarkdown : markdown).render(content),
    legacyHtml,
  );
export function ChatMarkdown({
  content,
}: {
  content: string;
}): React.JSX.Element {
  const [preview, setPreview] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  // The server and first client render share escaped text, then enhance it once
  // the browser DOM is available. This also supports non-DOM SDK consumers.
  if (!mounted || typeof DOMPurify.sanitize !== 'function') {
    return <div className="chat-markdown whitespace-pre-wrap">{content}</div>;
  }
  return (
    <>
      <div
        className="chat-markdown"
        dangerouslySetInnerHTML={{ __html: renderChatMarkdown(content) }}
        onClick={(event) => {
          const target = event.target;
          if (target instanceof HTMLImageElement) setPreview(target.src);
        }}
      />
      {preview && (
        <Image
          src={preview}
          alt=""
          className="hidden"
          preview={{
            visible: true,
            onVisibleChange: (visible) => {
              if (!visible) setPreview(null);
            },
          }}
        />
      )}
    </>
  );
}
