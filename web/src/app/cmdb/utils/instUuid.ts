/** 与后端 normalize_inst_uuid 对齐：仅接受小写带连字符的 UUIDv4。 */
const INST_UUID_V4_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export const isCmdbInstUuid = (value: unknown): value is string => {
  if (value === undefined || value === null) return false;
  const text = String(value).trim();
  return INST_UUID_V4_RE.test(text);
};

/** 从候选值中取第一个合法 inst_uuid；数字图 _id / 旧 inst_id 一律丢弃。 */
export const resolveCmdbInstUuid = (
  ...candidates: unknown[]
): string | null => {
  for (const candidate of candidates) {
    if (!isCmdbInstUuid(candidate)) continue;
    return String(candidate).trim().toLowerCase();
  }
  return null;
};
