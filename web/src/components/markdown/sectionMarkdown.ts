/** 监控插件指引 Markdown 预处理：去掉文档主标题，避免与抽屉标题重复。 */

/**
 * 去掉文首单独一行的 H1（`# title`）。
 * 抽屉标题已承载文档名，正文不再渲染同名 H1。
 */
export const stripLeadingH1 = (markdown: string): string => {
  if (!markdown) {
    return '';
  }
  return markdown.replace(/^#\s+[^\n]+(?:\n+|$)/, '').trim();
};
