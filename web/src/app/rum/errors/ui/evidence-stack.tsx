'use client';

import { useMemo, useState } from 'react';
import { Button } from 'antd';
import { CopyOutlined, DownOutlined, UpOutlined } from '@ant-design/icons';

import { useTranslation } from '@/utils/i18n';

export interface StackFrame {
  file?: string;
  filename?: string;
  functionName?: string;
  function?: string;
  line?: number;
  column?: number;
  resolved?: boolean;
}

function isAppFrame(file?: string): boolean {
  if (!file) return true;
  const lower = file.toLowerCase();
  return !(
    lower.includes('/node_modules/') ||
    lower.includes('webpack/runtime/') ||
    lower.includes('webpack/bootstrap') ||
    lower.includes('react-dom') ||
    /(?:^|[/.-])vendor(?:s)?(?:[./-]|$)/.test(lower)
  );
}

export function formatFullStackTrace(rawFrames: string, fallbackTitle?: string): string {
  try {
    const parsed = JSON.parse(rawFrames);
    if (!Array.isArray(parsed) || !parsed.length) return fallbackTitle || '';
    const lines = [fallbackTitle || 'Error'];
    for (const f of parsed) {
      const fn = f.functionName || f.function || '(anonymous)';
      const file = f.file || f.filename || 'unknown';
      const loc = f.line != null ? `:${f.line}${f.column != null ? `:${f.column}` : ''}` : '';
      lines.push(`    at ${fn} (${file}${loc})`);
    }
    return lines.join('\n');
  } catch {
    return fallbackTitle || '';
  }
}

export default function EvidenceStack({
  raw,
  embedded = false,
}: {
  raw: string;
  embedded?: boolean;
}) {
  const { t } = useTranslation();
  const frames = useMemo<StackFrame[]>(() => {
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.map((frame: StackFrame) => ({
        ...frame,
        file: frame.file || frame.filename,
        functionName: frame.functionName || frame.function,
      }));
    } catch {
      return [];
    }
  }, [raw]);

  const appFrames = frames.filter((f) => isAppFrame(f.file));
  const libraryFrames = frames.filter((f) => !isAppFrame(f.file));
  const [libOpen, setLibOpen] = useState(false);

  if (!frames.length) {
    if (embedded) {
      return (
        <div className="px-4 py-8 text-center text-xs text-[var(--color-text-3)]">
          {t('rum.errors.detail.stackEmpty', '没有可用栈帧')}
        </div>
      );
    }
    return (
      <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] px-3.5 py-6">
        <p className="m-0 text-sm text-[var(--color-text-3)]">
          {t('rum.errors.detail.stackEmpty', '没有可用栈帧')}
        </p>
      </div>
    );
  }

  function FrameRow({ frame, index }: { frame: StackFrame; index: number }) {
    return (
      <div className="flex items-start gap-3 px-3.5 py-2.5 transition-colors hover:bg-[var(--color-fill-2)]">
        <span className="mt-0.5 w-6 shrink-0 text-right font-mono text-[11px] tabular-nums text-[var(--color-text-4)]">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1 font-mono text-xs leading-relaxed">
          <span className="font-semibold text-[var(--color-text-1)]">{frame.functionName || '(anonymous)'}</span>
          <span className="ml-1.5 break-all text-[var(--color-text-3)]">at {frame.file || 'unknown'}</span>
          {frame.line ? (
            <span className="ml-1 font-medium text-[var(--color-primary)]">
              :{frame.line}
              {frame.column != null ? `:${frame.column}` : ''}
            </span>
          ) : null}
          {frame.resolved ? (
            <span className="ml-2 rounded bg-[color-mix(in_srgb,var(--color-success)_12%,var(--color-bg))] px-1 py-0.5 text-[10px] font-medium text-[var(--color-success)]">
              {t('rum.errors.detail.resolvedFrame', '已还原')}
            </span>
          ) : null}
        </div>
        <Button
          type="link"
          size="small"
          icon={<CopyOutlined aria-hidden="true" />}
          aria-label={t('common.copy', '复制')}
          onClick={() => {
            void navigator.clipboard.writeText(
              `${frame.functionName || 'anonymous'} (${frame.file || 'unknown'}:${frame.line ?? '?'}:${frame.column ?? '?'})`,
            );
          }}
        />
      </div>
    );
  }

  const containerClasses = embedded
    ? 'divide-y divide-[var(--color-border-2)] bg-[var(--color-bg)]'
    : 'overflow-hidden rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] divide-y divide-[var(--color-border-2)]';

  return (
    <div className={containerClasses}>
      {appFrames.map((frame, index) => (
        <FrameRow key={`app-${index}`} frame={frame} index={index} />
      ))}
      {libraryFrames.length > 0 ? (
        <>
          <button
            type="button"
            className="flex w-full items-center gap-2 bg-[var(--color-fill-1)]/40 px-3.5 py-2 text-left text-xs font-medium text-[var(--color-text-3)] transition-colors hover:bg-[var(--color-fill-1)]"
            onClick={() => setLibOpen((v) => !v)}
          >
            {libOpen ? <UpOutlined /> : <DownOutlined />}
            {t('rum.errors.detail.libraryFrames', '库栈帧')} ({libraryFrames.length})
          </button>
          {libOpen
            ? libraryFrames.map((frame, index) => (
              <FrameRow key={`lib-${index}`} frame={frame} index={appFrames.length + index} />
            ))
            : null}
        </>
      ) : null}
    </div>
  );
}
