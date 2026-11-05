export interface StoredChatAttachment {
  id: number;
  name: string;
  mime: string;
  size: number;
  status: string;
  failure_reason?: string;
}

const ACCEPT = new Set(['pdf', 'docx', 'pptx', 'xlsx', 'csv', 'txt', 'md', 'jpg', 'jpeg', 'png', 'gif', 'webp']);

export function chatAttachmentEndpoints(sseUrl: string): { upload: string; download: (id: number) => string; status: (id: number) => string } | null {
  try {
    const absolute = /^https?:\/\//i.test(sseUrl);
    const url = new URL(sseUrl, 'http://placeholder.local');
    const marker = '/skill_channel/';
    const index = url.pathname.indexOf(marker);
    if (index < 0) return null;
    const pathPrefix = url.pathname.slice(0, index);
    const prefix = absolute ? `${url.origin}${pathPrefix}` : pathPrefix;
    return {
      upload: `${prefix}/skill_channel/chat_attachment/upload/`,
      status: (id: number) => `${prefix}/skill_channel/chat_attachment/${id}/`,
      download: (id: number) => `${prefix}/skill_channel/chat_attachment/${id}/download/`,
    };
  } catch {
    return null;
  }
}

export function isAllowedChatFile(file: { name: string; size: number; type?: string }): boolean {
  const extension = file.name.includes('.') ? file.name.split('.').pop()?.toLowerCase() : '';
  if (!extension || !ACCEPT.has(extension)) return false;
  const image = ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(extension);
  return file.size <= (image ? 5 : 20) * 1024 * 1024;
}

export function jobDistributeEndpoints(sseUrl: string): { upload: string; list: string } | null {
  const endpoints = chatAttachmentEndpoints(sseUrl);
  if (!endpoints) return null;
  const prefix = endpoints.upload.replace(/\/skill_channel\/chat_attachment\/upload\/$/, '');
  return {
    upload: `${prefix}/skill_channel/job_distribute_file/upload/`,
    list: `${prefix}/skill_channel/job_distribute_file/`,
  };
}

export async function listJobDistributeFiles(
  sseUrl: string,
  sessionId: string,
  headers: HeadersInit,
): Promise<Array<{ id: number; name: string; size: number }>> {
  const endpoints = jobDistributeEndpoints(sseUrl);
  if (!endpoints) {
    throw new Error('缺少分发文件地址');
  }
  const query = new URLSearchParams({ session_id: sessionId });
  const response = await fetch(`${endpoints.list}?${query.toString()}`, {
    headers,
    credentials: 'include',
  });
  const payload = await response.json();
  if (!response.ok || payload?.result === false) {
    throw new Error(payload?.message || '暂存文件查询失败');
  }
  return Array.isArray(payload.data) ? payload.data : [];
}

export async function uploadJobDistributeFile(
  file: File,
  sseUrl: string,
  sessionId: string,
  headers: HeadersInit,
): Promise<{ id: number; name: string; size: number }> {
  const endpoints = jobDistributeEndpoints(sseUrl);
  if (!endpoints) {
    throw new Error('缺少分发文件地址');
  }
  const body = new FormData();
  body.append('file', file);
  body.append('session_id', sessionId);
  const requestHeaders = new Headers(headers);
  requestHeaders.delete('Content-Type');
  const response = await fetch(endpoints.upload, {
    method: 'POST',
    headers: requestHeaders,
    body,
    credentials: 'include',
  });
  const payload = await response.json();
  if (!response.ok || payload?.result === false) {
    throw new Error(payload?.message || '上传失败');
  }
  return payload.data as { id: number; name: string; size: number };
}

export async function uploadChatFile(file: File, sseUrl: string, headers: HeadersInit): Promise<StoredChatAttachment> {
  const endpoints = chatAttachmentEndpoints(sseUrl);
  if (!endpoints) {
    throw new Error('缺少附件上传地址');
  }
  const body = new FormData();
  body.append('file', file);
  const requestHeaders = new Headers(headers);
  requestHeaders.delete('Content-Type');
  const response = await fetch(endpoints.upload, { method: 'POST', headers: requestHeaders, body, credentials: 'include' });
  const payload = await response.json();
  if (!response.ok || payload?.result === false) {
    throw new Error(payload?.message || '上传失败');
  }
  return payload.data as StoredChatAttachment;
}

export async function fetchChatAttachmentStatus(id: number, sseUrl: string, headers: HeadersInit): Promise<StoredChatAttachment> {
  const endpoints = chatAttachmentEndpoints(sseUrl);
  if (!endpoints) {
    throw new Error('缺少附件状态地址');
  }
  const response = await fetch(endpoints.status(id), { headers, credentials: 'include' });
  const payload = await response.json();
  if (!response.ok || payload?.result === false) {
    throw new Error(payload?.message || '状态查询失败');
  }
  return payload.data as StoredChatAttachment;
}

export function attachmentMetadata(items: readonly StoredChatAttachment[]): StoredChatAttachment[] {
  return items.map((item) => ({
    id: item.id,
    name: item.name,
    mime: item.mime,
    size: item.size,
    status: item.status,
  }));
}
