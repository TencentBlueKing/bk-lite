export type ScanBatchKind = 'cmdb' | 'collect' | 'monitor';

export type ScanBatchResult = Record<string, number> & {
  items?: Array<{ status?: string; reason?: string; host?: string }>;
  collect?: Record<string, number>;
};

type Translate = (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string;

const toastOf = (kind: 'success' | 'warning', text: string) => ({ kind, text });

export const summarizeScanBatchResult = (t: Translate, kind: ScanBatchKind, result: ScanBatchResult) => {
  if (kind === 'cmdb') {
    const written = result?.written ?? 0;
    const skipped = result?.skipped ?? 0;
    const failed = result?.failed ?? 0;
    if (failed || skipped || written === 0) {
      return toastOf('warning', t('Scan.writeCmdbPartial', undefined, { written, skipped, failed }));
    }
    return toastOf('success', t('Scan.writeCmdbDone', undefined, { count: written }));
  }
  if (kind === 'collect') {
    const written = result?.written ?? 0;
    const created = result?.created ?? result?.collect?.created ?? 0;
    const appended = result?.appended ?? result?.collect?.appended ?? 0;
    const skipped = result?.collect?.skipped ?? result?.skipped ?? 0;
    const failed = result?.failed ?? result?.collect?.failed ?? 0;
    if (failed || skipped || appended || created === 0) {
      return toastOf(
        'warning',
        `${t('Scan.writeCmdbPartial', undefined, { written, skipped: result?.skipped ?? 0, failed: result?.failed ?? 0 })}；${t('Scan.generateCollectPartial', undefined, { created, appended, skipped, failed })}`
      );
    }
    return toastOf('success', t('Scan.generateCollectDone', undefined, { count: created }));
  }
  const pushed = result?.pushed ?? 0;
  const failed = result?.failed ?? 0;
  const skipped = result?.skipped ?? 0;
  const items = Array.isArray(result?.items) ? result.items : [];
  const reasons = items
    .filter((item) => item.status !== 'pushed' && item.reason)
    .slice(0, 3)
    .map((item) => `${item.host || '-'}: ${item.reason}`)
    .join('；');
  if (failed || skipped || pushed === 0) {
    const summary = t('Scan.pushMonitorPartial', undefined, { pushed, failed, skipped });
    return toastOf('warning', reasons ? `${summary}（${reasons}）` : summary);
  }
  return toastOf('success', t('Scan.pushMonitorDone', undefined, { count: pushed }));
};
