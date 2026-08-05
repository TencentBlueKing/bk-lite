/** Wiki 解析图片稳定路径 ↔ 展示 URL */

const WIKI_MEDIA_RE =
  /(?:\.\/|\/)?wiki\/media\/\d+\/\d+\/[a-f0-9]{16,}\.[a-z0-9]+/gi;

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function normalizeWikiMediaLocator(raw: string): string {
  let text = (raw || "").trim().replace(/\\/g, "/");
  while (text.startsWith("./")) text = text.slice(2);
  if (text.startsWith("/")) text = text.slice(1);
  return text;
}

export function collectWikiMediaLocators(markdown: string): string[] {
  if (!markdown) return [];
  const found = new Set<string>();
  // 兼容 locator=wiki/media/... 以及 locator=wiki%2Fmedia%2F...
  for (const match of markdown.matchAll(
    /(?:locator=)([^&\s"'<>\)]+)/gi,
  )) {
    let raw = match[1] || "";
    try {
      raw = decodeURIComponent(raw);
    } catch {
      // keep raw
    }
    if (/wiki\/media\/\d+\/\d+\/[a-f0-9]{16,}\.[a-z0-9]+/i.test(raw)) {
      found.add(normalizeWikiMediaLocator(raw));
    }
  }
  if (markdown.includes("wiki/media/")) {
    for (const match of markdown.matchAll(WIKI_MEDIA_RE)) {
      found.add(normalizeWikiMediaLocator(match[0]));
    }
  }
  return Array.from(found);
}

/** 把裸 wiki/media（及过期签名 URL）替换为可加载绝对 URL；保证全部 locator 都替换。 */
export function isWikiMediaDisplayUrl(url: string): boolean {
  const value = (url || "").trim();
  return (
    /^https?:\/\//i.test(value) ||
    value.startsWith("/api/proxy/opspilot/wiki_mgmt/media/")
  );
}

function replaceProxyMediaUrls(
  text: string,
  locator: string,
  signed: string,
): string {
  // 整段替换同源代理 URL，避免只替换 query 里的 locator 造成嵌套
  return text.replace(
    /\/api\/proxy\/opspilot\/wiki_mgmt\/media\/\?[^\s"'<>\)]*/gi,
    (match) => {
      let decoded = match;
      try {
        decoded = decodeURIComponent(match);
      } catch {
        // keep match
      }
      if (
        match.includes(locator) ||
        decoded.includes(locator) ||
        match.includes(encodeURIComponent(locator))
      ) {
        return signed;
      }
      return match;
    },
  );
}

export function applyWikiMediaDisplayUrls(
  markdown: string,
  urls: Record<string, string>,
): string {
  if (!markdown || !urls || !Object.keys(urls).length) return markdown || "";
  let text = markdown;
  const locators = Object.keys(urls).sort((a, b) => b.length - a.length);
  for (const locator of locators) {
    const signed = (urls[locator] || "").trim();
    if (!signed || signed === locator) continue;
    if (!isWikiMediaDisplayUrl(signed)) continue;
    // 1) http(s) 预签名整段替换
    text = text.replace(
      new RegExp(
        `https?:\\/\\/[^\\s"'<>\\])]*${escapeRegExp(locator)}[^\\s"'<>\\])]*`,
        "gi",
      ),
      signed,
    );
    // 2) 同源代理整段替换（禁止只替换 locator= 后的路径）
    text = replaceProxyMediaUrls(text, locator, signed);
    // 3) 裸 locator；排除 locator= / 路径片段（lookbehind 含 =）
    text = text.replace(
      new RegExp(
        `(?<![A-Za-z0-9\\-._/:=%])(?:\\.\\/|\\/)?${escapeRegExp(locator)}`,
        "g",
      ),
      signed,
    );
  }
  return text;
}

/** 改写后仍裸露的 locator（不含已在 http/proxy URL 内的路径片段） */
export function collectBareWikiMediaLocators(markdown: string): string[] {
  if (!markdown || !markdown.includes("wiki/media/")) return [];
  // lookbehind 含 =，避免把 ?locator=wiki/media/... 当成裸路径
  const re =
    /(?<![A-Za-z0-9\-._/:=%])(?:\.\/|\/)?wiki\/media\/\d+\/\d+\/[a-f0-9]{16,}\.[a-z0-9]+/gi;
  const found = new Set<string>();
  for (const match of markdown.matchAll(re)) {
    found.add(normalizeWikiMediaLocator(match[0]));
  }
  return Array.from(found);
}
