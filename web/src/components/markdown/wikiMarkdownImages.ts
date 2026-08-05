/**
 * 在 remark 之前抽出 Markdown / HTML 图片。
 * 用「URL 锚定」匹配，避免 alt 中的 ] 导致正则提前截断。
 */

const PROXY_OR_MEDIA_URL =
  /(\/api\/proxy\/opspilot\/wiki_mgmt\/media\/\?[^\s)"']+|https?:\/\/[^\s)"']+|\/?wiki\/media\/\d+\/\d+\/[a-f0-9]{16,}\.[a-z0-9]+)/i;

const HTML_IMG_RE =
  /<img\b([^>]*?)\bsrc\s*=\s*(["'])([^"']+)\2([^>]*)>/gi;

function escapeHtmlAttr(value: string): string {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function normalizeLocator(raw: string): string {
  let text = (raw || "").trim().replace(/\\/g, "/");
  while (text.startsWith("./")) text = text.slice(2);
  if (text.startsWith("/")) text = text.slice(1);
  return text;
}

function locatorFromDisplaySrc(src: string): string | null {
  const value = (src || "").trim();
  if (!value) return null;
  const fromQuery = /[?&]locator=([^&]+)/i.exec(value);
  if (fromQuery) {
    try {
      return normalizeLocator(decodeURIComponent(fromQuery[1]));
    } catch {
      return normalizeLocator(fromQuery[1]);
    }
  }
  const matched = value.match(
    /(?:\.\/|\/)?wiki\/media\/\d+\/\d+\/[a-f0-9]{16,}\.[a-z0-9]+/i,
  );
  return matched ? normalizeLocator(matched[0]) : null;
}

function isDisplayableSrc(src: string): boolean {
  const value = (src || "").trim();
  return (
    /^https?:\/\//i.test(value) ||
    value.startsWith("/api/proxy/opspilot/wiki_mgmt/media/")
  );
}

/**
 * 从后往前找与 url 匹配的 ![alt](url)：
 * 先定位 ](url)，再在左侧找最近的 ![，alt 允许包含 ]。
 */
export function extractMarkdownImages(markdown: string): {
  markdown: string;
  images: Array<{ alt: string; src: string }>;
} {
  const images: Array<{ alt: string; src: string }> = [];
  if (!markdown) {
    return { markdown: "", images };
  }

  const replacements: Array<{ start: number; end: number; token: string }> = [];
  const closePattern =
    /\]\((\/api\/proxy\/opspilot\/wiki_mgmt\/media\/\?[^\s)"']+|https?:\/\/[^\s)"']+|\/?wiki\/media\/\d+\/\d+\/[a-f0-9]{16,}\.[a-z0-9]+)\)/gi;

  let match: RegExpExecArray | null;
  while ((match = closePattern.exec(markdown)) !== null) {
    const url = (match[1] || "").trim();
    if (!url || !PROXY_OR_MEDIA_URL.test(url)) continue;
    const closeBracket = match.index; // points to ]
    const end = match.index + match[0].length;
    // 在 ] 之前找最近的 ![
    const head = markdown.lastIndexOf("![", closeBracket);
    if (head < 0 || head > closeBracket) continue;
    // 确保中间没有另一个未处理的图片起点干扰：允许 alt 含任意字符
    const alt = markdown.slice(head + 2, closeBracket);
    // 跳过已覆盖区间
    if (replacements.some((r) => head < r.end && end > r.start)) continue;
    const index = images.length;
    images.push({ alt, src: url });
    replacements.push({
      start: head,
      end,
      token: `\n\n@@WIKI_MD_IMG_${index}@@\n\n`,
    });
  }

  let next = markdown;
  for (const r of [...replacements].sort((a, b) => b.start - a.start)) {
    next = next.slice(0, r.start) + r.token + next.slice(r.end);
  }

  // 已是 HTML <img> 时也抽出
  next = next.replace(
    HTML_IMG_RE,
    (_whole, pre: string, _q: string, src: string, post: string) => {
      const value = (src || "").trim();
      if (!value) return _whole;
      const altMatched = /(?:^|\s)alt\s*=\s*(["'])([\s\S]*?)\1/i.exec(
        `${pre} ${post}`,
      );
      const index = images.length;
      images.push({ alt: altMatched?.[2] || "", src: value });
      return `\n\n@@WIKI_MD_IMG_${index}@@\n\n`;
    },
  );

  return { markdown: next, images };
}

export function restoreMarkdownImages(
  html: string,
  images: Array<{ alt: string; src: string }>,
): string {
  if (!html || !images.length) return html || "";
  let out = html;
  images.forEach((image, index) => {
    const token = `@@WIKI_MD_IMG_${index}@@`;
    const imgTag = `<img src="${escapeHtmlAttr(image.src)}" alt="${escapeHtmlAttr(image.alt)}" />`;
    out = out.replace(
      new RegExp(`<p>\\s*${token}\\s*</p>`, "g"),
      `<p>${imgTag}</p>`,
    );
    out = out.replaceAll(token, imgTag);
  });
  return out;
}

/** 若 HTML 里 img.src 仍是裸 wiki/media，用原文中的可展示 URL 回填。 */
export function repairBareWikiMediaImgSrcs(
  html: string,
  sourceMarkdown: string,
): string {
  if (!html || !sourceMarkdown) return html || "";
  const displayByLocator = new Map<string, string>();

  const register = (src: string) => {
    const value = (src || "").trim();
    if (!isDisplayableSrc(value)) return;
    const locator = locatorFromDisplaySrc(value);
    if (!locator) return;
    displayByLocator.set(locator, value);
  };

  // 用与 extract 相同的 URL 锚定方式收集
  const closePattern =
    /\]\((\/api\/proxy\/opspilot\/wiki_mgmt\/media\/\?[^\s)"']+|https?:\/\/[^\s)"']+)\)/gi;
  for (const match of sourceMarkdown.matchAll(closePattern)) {
    register((match[1] || "").trim());
  }
  for (const match of sourceMarkdown.matchAll(HTML_IMG_RE)) {
    register((match[3] || "").trim());
  }

  if (!displayByLocator.size) return html;

  return html.replace(
    /(<img\b[^>]*?\bsrc\s*=\s*")((?:\.\/|\/)?wiki\/media\/\d+\/\d+\/[a-f0-9]{16,}\.[a-z0-9]+)(")/gi,
    (whole, pre: string, src: string, post: string) => {
      const locator = normalizeLocator(src);
      const display = displayByLocator.get(locator);
      if (!display) return whole;
      return `${pre}${escapeHtmlAttr(display)}${post}`;
    },
  );
}
