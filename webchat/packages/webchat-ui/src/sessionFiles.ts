export type SessionAttachmentFile = {
  id: string;
  filename: string;
  fileUrl: string;
  ext: string;
};

type ToolCallLike = {
  id?: string;
  name?: string;
  result?: string;
};

type ContentChunkLike = {
  type?: string;
  toolCalls?: ToolCallLike[];
};

type MessageLike = {
  id?: string;
  metadata?: { contentChunks?: ContentChunkLike[] } | null;
};

function parseAttachmentResult(result: string): { filename?: string; file_url?: string } | null {
  try {
    const parsed = JSON.parse(result) as { filename?: string; file_url?: string };
    if (parsed && typeof parsed === 'object') {
      return parsed;
    }
  } catch {
    const filename = result.match(/["']filename["']\s*:\s*["']([^"']+)["']/)?.[1];
    const fileUrl = result.match(/["']file_url["']\s*:\s*["']([^"']+)["']/)?.[1];
    if (filename || fileUrl) {
      return { filename, file_url: fileUrl };
    }
  }
  return null;
}

export function fileExtension(filename: string): string {
  const dot = filename.lastIndexOf('.');
  if (dot <= 0 || dot === filename.length - 1) {
    return '';
  }
  return filename.slice(dot + 1).toLowerCase();
}

export function collectSessionAttachmentFiles(messages: MessageLike[]): SessionAttachmentFile[] {
  const seen = new Set<string>();
  const files: SessionAttachmentFile[] = [];
  for (const message of messages) {
    const chunks = message.metadata?.contentChunks;
    if (!Array.isArray(chunks)) {
      continue;
    }
    for (const chunk of chunks) {
      if (chunk?.type !== 'toolCalls' || !Array.isArray(chunk.toolCalls)) {
        continue;
      }
      for (const tool of chunk.toolCalls) {
        if (tool?.name !== 'generate_attachment_file' || !tool.result) {
          continue;
        }
        const parsed = parseAttachmentResult(tool.result);
        const fileUrl = parsed?.file_url || '';
        const filename = parsed?.filename || '';
        if (!fileUrl || !filename || seen.has(fileUrl)) {
          continue;
        }
        seen.add(fileUrl);
        files.push({
          id: tool.id || fileUrl,
          filename,
          fileUrl,
          ext: fileExtension(filename),
        });
      }
    }
  }
  return files;
}
