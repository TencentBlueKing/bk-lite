'use client';

import React, { useMemo, useState } from 'react';
import { WC } from '../chrome';
import { fileExtension, openSafeDownload, type SessionAttachmentFile } from '../sessionFiles';
import { useTranslator } from '../useTranslator';

const FILE_BADGE: Record<string, { label: string; color: string }> = {
  doc: { label: 'W', color: 'var(--color-primary, #155AEF)' },
  docx: { label: 'W', color: 'var(--color-primary, #155AEF)' },
  xls: { label: 'X', color: 'var(--color-success, #27c274)' },
  xlsx: { label: 'X', color: 'var(--color-success, #27c274)' },
  csv: { label: 'X', color: 'var(--color-success, #27c274)' },
  ppt: { label: 'P', color: 'var(--color-warning, #ff7d00)' },
  pptx: { label: 'P', color: 'var(--color-warning, #ff7d00)' },
  pdf: { label: 'P', color: 'var(--color-fail, #F43B2C)' },
  txt: { label: 'T', color: 'var(--color-text-3, #7588a3)' },
  md: { label: 'M', color: 'var(--color-text-3, #7588a3)' },
};

function formatGeneratedAt(timestamp: number): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export const SessionFileBar: React.FC<{
  files: SessionAttachmentFile[];
  onClose?: () => void;
}> = ({ files, onClose }) => {
  const t = useTranslator();
  const [query, setQuery] = useState('');
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return files;
    }
    return files.filter((file) => file.filename.toLowerCase().includes(needle) || (file.source || '').toLowerCase().includes(needle));
  }, [files, query]);

  return (
    <div className="flex h-full min-h-0 w-full flex-col" style={{ background: WC.stage }}>
      <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-3">
        <div className="text-sm font-medium" style={{ color: WC.headerInk }}>
          {t('chat.generatedFiles', '已生成文件')}
          <span className="ml-1.5 font-normal" style={{ color: WC.muted }}>{files.length}</span>
        </div>
        {onClose ? (
          <button
            type="button"
            className="flex h-6 w-6 items-center justify-center rounded-md text-sm hover:bg-[var(--color-fill-2,#f4f5f8)]"
            style={{ color: WC.muted }}
            aria-label={t('chat.closeGeneratedFiles', '关闭文件列表')}
            onClick={onClose}
          >
            ✕
          </button>
        ) : null}
      </div>
      <div className="px-3 pb-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('chat.searchGeneratedFiles', '搜索文件……')}
          className="w-full rounded-md border px-2 py-1.5 text-xs outline-none"
          style={{ borderColor: WC.botBorder, color: WC.headerInk, background: WC.stage }}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {files.length === 0 ? (
          <p className="px-1 py-6 text-center text-xs" style={{ color: WC.muted }}>
            {t('chat.noGeneratedFiles', '当前会话还没有生成文件')}
          </p>
        ) : visible.length === 0 ? (
          <p className="px-1 py-6 text-center text-xs" style={{ color: WC.muted }}>
            {t('chat.noMatchingFiles', '没有匹配的文件')}
          </p>
        ) : visible.map((file) => {
          const ext = file.ext || fileExtension(file.filename);
          const badge = FILE_BADGE[ext] || { label: ext.slice(0, 1).toUpperCase() || 'F', color: WC.muted };
          const generatedAt = typeof file.createdAt === 'number' ? formatGeneratedAt(file.createdAt) : '';
          return (
            <div
              key={file.id}
              className="mb-1.5 flex items-start gap-2 rounded-lg px-2 py-2"
              style={{ background: WC.page }}
            >
              <span
                className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-xs font-semibold"
                style={{ color: badge.color, background: 'color-mix(in srgb, currentColor 12%, transparent)' }}
                aria-hidden
              >
                {badge.label}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px]" style={{ color: WC.headerInk }} title={file.filename}>
                  {file.filename}
                </div>
                {generatedAt ? (
                  <div className="mt-0.5 truncate text-[11px]" style={{ color: WC.muted }}>
                    {t('chat.fileGeneratedAt', '生成时间 {time}', { time: generatedAt })}
                  </div>
                ) : null}
                {file.source ? (
                  <div className="truncate text-[11px]" style={{ color: WC.muted }} title={file.source}>
                    {t('chat.fileSource', '对话：{source}', { source: file.source })}
                  </div>
                ) : null}
              </div>
              <button
                type="button"
                className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md hover:bg-[var(--color-fill-2,#f4f5f8)]"
                style={{ color: WC.indigo }}
                aria-label={t('chat.downloadFile', '下载 {name}', { name: file.filename })}
                onClick={() => openSafeDownload(file)}
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
