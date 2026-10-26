import { z } from 'zod';

const customSchema = z.object({
  mode: z.literal('custom'),
  keys: z.array(z.string().min(1).max(200)).min(1).max(24)
});
const bkDisplayMetricsValueSchema = customSchema;

export type BkDisplayMetrics = z.infer<typeof bkDisplayMetricsValueSchema>;

/** Missing or empty selections stay unset. Invalid values do not reject the diagram. */
export function normalizeBkDisplayMetrics(value: unknown): BkDisplayMetrics | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const record = value as { mode?: unknown; keys?: unknown };
  if (record.mode !== 'custom' || !Array.isArray(record.keys)) return undefined;
  const keys = record.keys
    .filter((key): key is string => typeof key === 'string' && key.length > 0 && key.length <= 200)
    .slice(0, 24);
  if (!keys.length) return undefined;
  return { mode: 'custom', keys };
}

export const bkDisplayMetricsSchema = z.preprocess(
  (value) => normalizeBkDisplayMetrics(value),
  bkDisplayMetricsValueSchema.optional()
);
