import type { CustomChatMessage, ReportFileDownload } from '@/app/opspilot/types/global';

import { isRenderableReportDownload } from './downloadUrl';

export type SessionFileItem = ReportFileDownload & {
  source?: string;
};

export function collectSessionFiles(messages: CustomChatMessage[]): SessionFileItem[] {
  const seen = new Set<string>();
  const files: SessionFileItem[] = [];
  let source = '';
  for (const message of messages) {
    if (message.role === 'user' && message.content.trim()) {
      source = message.content.trim();
    }
    for (const download of message.reportFileDownloads || []) {
      if (!isRenderableReportDownload(download)) {
        continue;
      }
      const key = download.file_url || download.download_id;
      if (!key || seen.has(key)) {
        continue;
      }
      seen.add(key);
      files.push({ ...download, source: source || undefined });
    }
  }
  return files;
}

export function fileExtension(filename: string): string {
  const dot = filename.lastIndexOf('.');
  if (dot <= 0 || dot === filename.length - 1) {
    return '';
  }
  return filename.slice(dot + 1).toLowerCase();
}
