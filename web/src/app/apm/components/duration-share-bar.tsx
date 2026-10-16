'use client';

import { theme } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';

export interface DurationShareSegment {
  key: string;
  label: string;
  durationMs: number;
  detail?: string;
}

export default function DurationShareBar({
  segments,
  caption,
}: {
  segments: DurationShareSegment[];
  caption?: string;
}) {
  const { token } = theme.useToken();
  const colors = [token.colorSuccess, token.colorWarning, token.colorPrimary, token.colorInfo, token.colorError];
  const total = segments.reduce((sum, segment) => sum + Math.max(0, segment.durationMs), 0);
  if (total <= 0) return null;

  return (
    <div>
      <div
        className="flex h-5 items-stretch gap-0.5 overflow-hidden rounded-md border border-[var(--color-border)]/40 bg-[var(--color-fill-1)] p-0.5 shadow-2xs"
        role="img"
        aria-label="耗时构成占比条"
      >
        {segments.map((segment, index) => {
          const pct = Math.round((Math.max(0, segment.durationMs) / total) * 100);
          return (
            <span
              key={segment.key}
              title={`${segment.label}: ${pct}%${segment.detail ? ` (${segment.detail})` : ''}`}
              className="relative flex h-full min-w-1 items-center justify-center overflow-hidden rounded-[3px] transition-all duration-150 hover:brightness-110"
              style={{
                width: `${(Math.max(0, segment.durationMs) / total) * 100}%`,
                background: colors[index % colors.length],
              }}
            >
              {pct >= 10 ? (
                <span className="pointer-events-none truncate px-1 text-[10px] font-bold tracking-wide text-white drop-shadow-2xs select-none">
                  {pct}%
                </span>
              ) : null}
            </span>
          );
        })}
      </div>
      <div className="mt-2.5 flex flex-wrap gap-2">
        {segments.map((segment, index) => {
          const pct = Math.round((Math.max(0, segment.durationMs) / total) * 100);
          return (
            <span
              key={segment.key}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border)]/50 bg-[var(--color-bg)] px-2.5 py-1 text-xs shadow-2xs transition-colors hover:border-[var(--color-border)]"
            >
              <span
                className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: colors[index % colors.length] }}
                aria-hidden="true"
              />
              <span className="font-medium text-[var(--color-text-1)]">{segment.label}</span>
              <span className="rounded bg-[var(--color-fill-1)] px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-[var(--color-text-2)]">
                {pct}%
              </span>
              {segment.detail ? (
                <span className="text-[11px] tabular-nums text-[var(--color-text-3)]">
                  · {segment.detail}
                </span>
              ) : null}
            </span>
          );
        })}
      </div>
      {caption ? (
        <div className="mt-2.5 flex items-start gap-1.5 rounded-md border border-[var(--color-border)]/35 bg-[var(--color-fill-1)]/30 px-2.5 py-1.5 text-xs text-[var(--color-text-3)]">
          <InfoCircleOutlined className="mt-0.5 shrink-0 text-[var(--color-text-3)]" aria-hidden="true" />
          <span>{caption}</span>
        </div>
      ) : null}
    </div>
  );
}
