export const CHAT_ATTACHMENT_ACCEPT = '.pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.jpg,.jpeg,.png,.gif,.webp';
export const MAX_CHAT_ATTACHMENTS = 5;
const IMAGE_MAX_BYTES = 5 * 1024 * 1024;
const DOCUMENT_MAX_BYTES = 20 * 1024 * 1024;

export interface ChatAttachmentMeta {
  id: number;
  name: string;
  mime: string;
  size: number;
  status: 'pending' | 'ready' | 'failed' | string;
  failure_reason?: string;
  previewUrl?: string;
}

const UPLOAD_URL = '/api/proxy/opspilot/skill_channel/chat_attachment/upload/';

export function isImageMime(mime: string): boolean {
  return mime.startsWith('image/');
}

export function clientFileError(file: File, currentCount: number): string | null {
  if (currentCount >= MAX_CHAT_ATTACHMENTS) {
    return '单条消息最多 5 个附件';
  }
  const extension = file.name.includes('.') ? file.name.split('.').pop()?.toLowerCase() : '';
  const allowed = CHAT_ATTACHMENT_ACCEPT.split(',').map((item) => item.slice(1));
  if (!extension || !allowed.includes(extension)) {
    return '不支持的文件类型';
  }
  const limit = isImageMime(file.type) || ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(extension || '')
    ? IMAGE_MAX_BYTES
    : DOCUMENT_MAX_BYTES;
  if (file.size > limit) {
    return isImageMime(file.type) || limit === IMAGE_MAX_BYTES ? '图片大小不能超过 5MB' : '文件大小不能超过 20MB';
  }
  return null;
}

function authHeaders(token: string | null, extra?: Record<string, string>): Headers {
  const headers = new Headers(extra);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return headers;
}

export async function uploadChatAttachment(file: File, token: string | null): Promise<ChatAttachmentMeta> {
  const body = new FormData();
  body.append('file', file);
  const response = await fetch(UPLOAD_URL, {
    method: 'POST',
    headers: authHeaders(token),
    body,
    credentials: 'include',
  });
  const payload = await response.json();
  if (!response.ok || payload?.result === false) {
    throw new Error(payload?.message || '上传失败');
  }
  return payload.data as ChatAttachmentMeta;
}

export async function fetchChatAttachmentStatus(id: number, token: string | null): Promise<ChatAttachmentMeta> {
  const response = await fetch(`/api/proxy/opspilot/skill_channel/chat_attachment/${id}/`, {
    headers: authHeaders(token),
    credentials: 'include',
  });
  const payload = await response.json();
  if (!response.ok || payload?.result === false) {
    throw new Error(payload?.message || '状态查询失败');
  }
  return payload.data as ChatAttachmentMeta;
}

export async function downloadChatAttachmentBlob(id: number, token: string | null): Promise<Blob> {
  const response = await fetch(`/api/proxy/opspilot/skill_channel/chat_attachment/${id}/download/`, {
    headers: authHeaders(token),
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('下载失败');
  }
  return response.blob();
}
