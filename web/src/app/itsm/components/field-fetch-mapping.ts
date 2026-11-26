/** 只从实际测试样本推导可选路径，不执行表达式。 */
export interface SamplePath { value: string; label: string; type: string }
export function samplePaths(value: unknown, prefix = '', depth = 0): SamplePath[] {
  if (depth > 10) return [];
  const type = Array.isArray(value) ? 'array' : value === null ? 'null' : typeof value;
  const own = [{ value: prefix, label: `${prefix || '整个返回值'} · ${type}`, type }];
  if (Array.isArray(value)) return [...own, ...value.slice(0, 1).flatMap((v, i) => samplePaths(v, prefix ? `${prefix}.${i}` : `${i}`, depth + 1))];
  if (value && typeof value === 'object') return [...own, ...Object.entries(value).flatMap(([k, v]) => samplePaths(v, prefix ? `${prefix}.${k}` : k, depth + 1))];
  return own;
}
export function sampleAt(sample: unknown, path: string): unknown {
  return path ? path.split('.').reduce<unknown>((v, k) => v && typeof v === 'object' ? (v as Record<string, unknown>)[k] : undefined, sample) : sample;
}
export function listPath(sample: unknown): string | undefined {
  const paths = samplePaths(sample).filter(p => p.type === 'array' && !p.value.includes('.0.'));
  return paths.length === 1 ? paths[0].value : paths.find(p => /(^|\.)(items|results|list)$/.test(p.value))?.value;
}
export function compatiblePaths(paths: SamplePath[], type: string): SamplePath[] {
  return paths.filter(p => type === 'number' ? p.type === 'number' : type === 'string' ? p.type === 'string' : ['string', 'number'].includes(p.type));
}
