import type { PipelineDegradation } from '@/app/rum/lib/degradation';
import { degradationReason } from '@/app/rum/lib/degradation';

/**
 * DESIGN / RUM acceptance page chrome states.
 * Spec: loading / empty / degraded / forbidden (forbidden maps through error copy).
 * DESIGN: loading / empty / error (+ retry) / permission denied.
 */
export type RumPageState = 'loading' | 'empty' | 'error' | 'degraded' | 'ready';

export interface RumPageStateInput {
  pending: boolean;
  error?: string | null;
  itemCount: number;
  page?: PipelineDegradation | null;
}

/**
 * Resolve exclusive list/detail chrome. Priority:
 * loading → error → degraded (soft) → empty → ready.
 * Soft degradation still allows empty/ready rows; callers may show banner + content.
 */
export function resolveRumPageState(input: RumPageStateInput): RumPageState {
  if (input.pending) return 'loading';
  if (input.error) return 'error';
  const degrade = degradationReason(input.page);
  if (degrade && input.itemCount === 0) return 'degraded';
  if (input.itemCount === 0) return 'empty';
  return 'ready';
}

/** Soft banner reason when rows may still render. */
export function softDegradation(
  page: PipelineDegradation | null | undefined,
): 'control' | 'analytics' | null {
  return degradationReason(page);
}
