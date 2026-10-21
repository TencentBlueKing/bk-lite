'use client';

import React, { useMemo, useState } from 'react';
import { useTranslation } from '@/utils/i18n';

import { triggerReportDownload } from './downloadUrl';
import { fileExtension, type SessionFileItem } from './sessionFiles';

const FILE_BADGE: Record<string, { label: string; color: string }> = {
  doc: { label: 'W', color: 'var(--color-primary)' },
  docx: { label: 'W', color: 'var(--color-primary)' },
  xls: { label: 'X', color: 'var(--color-success)' },
  xlsx: { label: 'X', color: 'var(--color-success)' },
  csv: { label: 'X', color: 'var(--color-success)' },
  ppt: { label: 'P', color: 'var(--color-warning, #ff7d00)' },
  pptx: { label: 'P', color: 'var(--color-warning, #ff7d00)' },
  pdf: { label: 'P', color: 'var(--color-fail)' },
  txt: { label: 'T', color: 'var(--color-text-3)' },
  md: { label: 'M', color: 'var(--color-text-3)' },
};

function formatGeneratedAt(timestamp: number): string {
  const date = new Date(timestamp);
  if (!Number.isFinite(timestamp) || Number.isNaN(date.getTime())) {
    return '';
  }
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

const SessionFileBar: React.FC<{ files: SessionFileItem[] }> = ({ files }) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return files;
    }
    return files.filter((file) => (
      file.filename.toLowerCase().includes(needle)
      || (file.source || '').toLowerCase().includes(needle)
    ));
  }, [files, query]);

  if (files.length === 0) {
    return null;
  }

  return (
    <div className="mb-2 overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)]">
      <div className="flex items-center justify-between px-3 pb-2 pt-2.5">
        <span className="text-[13px] font-medium text-[var(--color-text-1)]">
          {t('chat.generatedFiles', '已生成文件')}
          <span className="ml-1.5 font-normal text-[var(--color-text-3)]">{files.length}</span>
        </span>
      </div>
      <div className="px-3 pb-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('chat.searchGeneratedFiles', '搜索文件…')}
          className="w-full rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] px-2 py-1.5 text-xs text-[var(--color-text-1)] outline-none"
        />
      </div>
      <div className="max-h-52 overflow-y-auto px-2 pb-2">
        {visible.length === 0 ? (
          <p className="px-1 py-4 text-center text-xs text-[var(--color-text-3)]">
            {t('chat.noMatchingFiles', '没有匹配的文件')}
          </p>
        ) : visible.map((file) => {
          const ext = fileExtension(file.filename);
          const badge = FILE_BADGE[ext] || { label: ext.slice(0, 1).toUpperCase() || 'F', color: 'var(--color-text-3)' };
          const generatedAt = formatGeneratedAt(file.received_at);
          return (
            <div
              key={file.file_url || file.download_id}
              className="mb-1.5 flex items-start gap-2 rounded-lg bg-[var(--color-fill-1)] px-2 py-2"
            >
              <span
                className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-xs font-semibold"
                style={{ color: badge.color, background: 'color-mix(in srgb, currentColor 12%, transparent)' }}
                aria-hidden
              >
                {badge.label}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] text-[var(--color-text-1)]" title={file.filename}>
                  {file.filename}
                </div>
                {generatedAt ? (
                  <div className="mt-0.5 truncate text-[11px] text-[var(--color-text-3)]">
                    {t('chat.fileGeneratedAt', '生成时间 {time}', { time: generatedAt })}
                  </div>
                ) : null}
                {file.source ? (
                  <div className="truncate text-[11px] text-[var(--color-text-3)]" title={file.source}>
                    {t('chat.fileSource', '对话：{source}', { source: file.source })}
                  </div>
                ) : null}
              </div>
              <button
                type="button"
                className="mt-1 flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-[var(--color-primary)] hover:bg-[var(--color-fill-2)]"
                aria-label={t('chat.downloadFile', '下载')}
                onClick={() => triggerReportDownload(file)}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M12 3v12" />
                  <path d="m7 11 5 5 5-5" />
                  <path d="M5 21h14" />
                </svg>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default SessionFileBar;
