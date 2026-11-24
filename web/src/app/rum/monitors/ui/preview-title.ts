export interface PreviewTitleInput {
  application: string;
  severityLabel: string;
  metricLabel: string;
  warnLabel: string;
  criticalLabel: string;
  warn: string;
  critical: string;
  comparator: string;
  unit: string;
}

function present(value: string): string {
  const trimmed = value.trim();
  return trimmed || '—';
}

function formatThreshold(raw: string, unit: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return '—';
  const numeric = Number(trimmed);
  if (!Number.isFinite(numeric)) return '—';
  return `${String(numeric)}${unit}`;
}

export function previewOutgoingTitle(input: PreviewTitleInput): string {
  const criticalValue = formatThreshold(input.critical, input.unit);
  const head = [
    `[${present(input.severityLabel)}]`,
    present(input.application),
    present(input.metricLabel),
    `${present(input.warnLabel)} ${formatThreshold(input.warn, input.unit)}`,
    `· ${present(input.criticalLabel)} ${criticalValue}`,
  ].join(' ');
  return `${head}（阈 ${present(input.comparator)} ${criticalValue}）`;
}
