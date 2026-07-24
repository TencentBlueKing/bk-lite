/**
 * 会话历史接口为兼容旧数据会尝试 JSON 反序列化，因此同一字段可能返回
 * 字符串、数组、对象或数字。页面渲染统一转换为文本后再走既有解析逻辑。
 */
export const toHistoryContentText = (content: unknown): string => {
  if (content === null || content === undefined) return '';
  if (typeof content === 'string') return content;

  if (typeof content === 'object') {
    try {
      return JSON.stringify(content);
    } catch {
      return String(content);
    }
  }

  return String(content);
};
