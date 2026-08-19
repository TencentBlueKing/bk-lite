/** 工具结果是否应展示为失败（凭据/配置/JSON error 等）。 */
export const isToolResultErrorContent = (content: string): boolean => {
  const text = String(content || '').trim();
  if (!text) return false;
  if (/"error"\s*:/.test(text)) return true;
  if (
    /无法加载\s*kubernetes|请检查 kubeconfig|unauthorized|\b401\b|\b403\b|invalid[_\s-]?credentials|permission denied|AttributeError|TypeError|decrypt failed|解密失败/i.test(
      text
    )
  ) {
    return true;
  }
  if (/^error[:\s]/i.test(text) || /^exception[:\s]/i.test(text)) return true;
  return false;
};
