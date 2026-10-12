'use client';

import React, { useState } from 'react';
import { WC } from '../chrome';
import { fileExtension, type SessionAttachmentFile } from '../sessionFiles';
import { useTranslator } from '../useTranslator';

function downloadFile(file: SessionAttachmentFile) {
  const link = document.createElement('a');
  link.href = file.fileUrl;
  link.setAttribute('download', file.filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export const SessionFileBar: React.FC<{ files: SessionAttachmentFile[] }> = ({ files }) => {
  const { t } = useTranslator();
  const [open, setOpen] = useState(true);
  if (files.length === 0) {
    return null;
  }

  return (
    <div
      className="mb-2 overflow-hidden rounded-lg"
      style={{ border: `1px solid ${WC.botBorder}`, background: WC.stage }}
    >
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
      >
        <span className="text-[13px] font-medium" style={{ color: WC.headerInk }}>
          {open ? '▾' : '▸'} {t('chat.sessionFiles', '本会话文件')}
          <span className="ml-2 font-normal" style={{ color: WC.muted }}>
            {files.length}
          </span>
        </span>
      </button>
      {open ? (
        <div className="max-h-[132px] overflow-y-auto" style={{ borderTop: `1px solid ${WC.thinkLine}` }}>
          {files.map((file) => (
            <div
              key={file.id}
              className="flex items-center justify-between gap-3 px-3 py-2"
              style={{ borderTop: `1px solid ${WC.thinkLine}` }}
            >
              <div className="min-w-0">
                <div className="truncate text-[13px]" style={{ color: WC.headerInk }}>
                  {file.filename}
                </div>
                <div className="text-xs" style={{ color: WC.muted }}>
                  {file.ext || fileExtension(file.filename)}
                </div>
              </div>
              <button
                type="button"
                className="shrink-0 text-xs"
                style={{ color: WC.indigo }}
                onClick={() => downloadFile(file)}
              >
                {t('chat.downloadFile', '下载')}
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
};
