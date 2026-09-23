'use client';

import type { RumViewMom } from '@/app/rum/api';
import Sparkline from '@/app/apm/components/home/sparkline';

export default function MomCell({ mom }: { mom: RumViewMom }) {
  const spark = mom.spark || [];
  if (spark.length === 0 || spark.every((v) => v <= 0)) {
    return <span className="text-[var(--color-text-3)]">—</span>;
  }
  return (
    <div className="flex items-center justify-center">
      <Sparkline data={spark} width={56} height={14} color="var(--color-text-3)" fit="fixed" kind="area" />
    </div>
  );
}
