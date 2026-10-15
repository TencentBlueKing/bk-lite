import type { DownloadableArtifact } from './types';

export async function downloadExecutionArtifact(
  get: <T>(url: string, config?: { responseType?: 'blob' }) => Promise<T>,
  artifact: Pick<DownloadableArtifact, 'download_url' | 'filename'>,
) {
  const blob = await get<Blob>(artifact.download_url, { responseType: 'blob' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = artifact.filename;
  link.click();
  URL.revokeObjectURL(url);
}
