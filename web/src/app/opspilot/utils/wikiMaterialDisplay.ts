/** 判断 AI 解读是否只是解析正文的截断/重复（含图片 markdown 时几乎一定是）。 */
export function isRedundantWikiAiSummary(
  parsedMarkdown: string | undefined | null,
  aiSummary: string | undefined | null,
): boolean {
  const summary = (aiSummary || "").trim();
  const parsed = (parsedMarkdown || "").trim();
  if (!summary) return true;
  if (!parsed) return false;
  // 完整或截断的图片 markdown（截断时常停在 alt 中间，没有 ](）
  if (
    /!\[/.test(summary) ||
    /(?:\.\/|\/)?wiki\/media\//i.test(summary) ||
    /\/api\/proxy\/opspilot\/wiki_mgmt\/media\//i.test(summary)
  ) {
    return true;
  }
  // 摘要等于正文前缀，或正文以摘要开头
  if (parsed.startsWith(summary)) return true;
  const head = parsed.slice(0, Math.min(120, parsed.length));
  if (head && summary.startsWith(head)) return true;
  const probe = summary.slice(0, Math.min(80, summary.length));
  if (probe.length >= 40 && parsed.includes(probe)) return true;
  return false;
}

/** 详情正文只取一份：优先完整解析正文，否则回退 AI 解读。 */
export function pickWikiMaterialBodyMarkdown(
  parsedMarkdown: string | undefined | null,
  aiSummary: string | undefined | null,
): string {
  const parsed = (parsedMarkdown || "").trim();
  if (parsed) return parsedMarkdown || "";
  return (aiSummary || "").trim() ? aiSummary || "" : "";
}
