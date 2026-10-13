import type { CustomChatMessage, ReportFileDownload } from '@/app/opspilot/types/global';

import { isRenderableReportDownload } from './downloadUrl';

export function collectSessionFiles(messages: CustomChatMessage[]): ReportFileDownload[] {
  const seen = new Set<string>();
  const files: ReportFileDownload[] = [];
  for (const message of messages) {
    for (const download of message.reportFileDownloads || []) {
      if (!isRenderableReportDownload(download)) {
        continue;
      }
      const key = download.file_url || download.download_id;
      if (!key || seen.has(key)) {
        continue;
      }
      seen.add(key);
      files.push(download);
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
