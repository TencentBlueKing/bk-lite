const OMITTED = '[已省略]';

/** 页面快照写入模型前去掉口令 / token，不截断整行。 */
export const redactSensitiveText = (value: string): string => {
  if (!value) return value;
  return value
    .replace(/Bearer\s+\S+/gi, `Bearer ${OMITTED}`)
    .replace(
      /\b(?:password|passwd|api_key|apikey|secret|token)\b\s*[:=]\s*\S+/gi,
      `key=${OMITTED}`,
    );
};
