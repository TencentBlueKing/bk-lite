'use client';

import React, { useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import type { ReportFileDownload } from '@/app/opspilot/types/global';

import { triggerReportDownload } from './downloadUrl';
import { fileExtension } from './sessionFiles';

interface SessionFileBarProps {
  files: ReportFileDownload[];
}

const SessionFileBar: React.FC<SessionFileBarProps> = ({ files }) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);
  if (files.length === 0) {
    return null;
  }

  return (
    <div className="mb-2 overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)]">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-1.5 text-left"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
      >
        <span className="text-xs font-medium text-[var(--color-text-1)]">
          {open ? '▾' : '▸'} {t('chat.sessionFiles', '本会话文件')}
          <span className="ml-2 font-normal text-[var(--color-text-3)]">{files.length}</span>
        </span>
      </button>
      {open ? (
        <div className="max-h-[72px] overflow-y-auto border-t border-[var(--color-border-1)]">
          {files.map((file) => {
            const ext = fileExtension(file.filename);
            return (
              <div
                key={file.file_url || file.download_id}
                className="flex min-w-0 items-center gap-2 border-t border-[var(--color-border-1)] px-3 py-1 first:border-t-0"
              >
                <span className="min-w-0 flex-1 truncate text-xs text-[var(--color-text-1)]">{file.filename}</span>
                {ext ? <span className="shrink-0 text-[11px] text-[var(--color-text-4)]">{ext}</span> : null}
                <button
                  type="button"
                  className="shrink-0 cursor-pointer rounded px-1.5 py-0.5 text-xs text-[var(--color-primary)] transition-colors hover:bg-[var(--color-fill-2)]"
                  onClick={() => triggerReportDownload(file)}
                >
                  {t('chat.downloadFile', '下载')}
                </button>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};

export default SessionFileBar;
