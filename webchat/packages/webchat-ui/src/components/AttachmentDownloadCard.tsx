'use client';

import React from 'react';
import type { SessionAttachmentFile } from '../sessionFiles';
import { useTranslator } from '../useTranslator';

function downloadFile(file: SessionAttachmentFile) {
  const link = document.createElement('a');
  link.href = file.fileUrl;
  link.setAttribute('download', file.filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export const AttachmentDownloadCards: React.FC<{ files: SessionAttachmentFile[] }> = ({ files }) => {
  const t = useTranslator();
  if (files.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {files.map((file) => (
        <button
          key={file.id}
          type="button"
          className="inline-flex cursor-pointer items-center gap-1 rounded border border-[var(--color-primary)] bg-[var(--color-primary-bg)] px-2 py-0.5 text-xs text-[var(--color-primary)] hover:bg-[var(--color-fill-2)]"
          onClick={() => downloadFile(file)}
        >
          {file.filename}
          <span aria-hidden>↓</span>
          <span className="sr-only">{t('chat.downloadFile', '下载')}</span>
        </button>
      ))}
    </div>
  );
};
