type Translate = (id: string, fallback?: string) => string;

const RETENTION_REASON_I18N: Record<string, { id: string; fallback: string }> = {
  明细保留期不足: { id: 'apm.slo.retentionTooShort', fallback: '明细保留期不足' },
  明细保留期配置无效: { id: 'apm.slo.retentionInvalid', fallback: '明细保留期配置无效' },
};

export function sloRetentionLabel(reason: string | null | undefined, t: Translate): string | null {
  const item = reason ? RETENTION_REASON_I18N[reason] : undefined;
  if (!item) return null;
  return t(item.id, item.fallback);
}
