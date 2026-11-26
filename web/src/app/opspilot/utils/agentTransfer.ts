export const AGENT_IMPORT_NOTES_KEY = 'opspilot-agent-import-notes';

export function rememberAgentImportNotes(notes: string[]) {
  if (typeof window === 'undefined') {
    return;
  }
  if (!notes.length) {
    sessionStorage.removeItem(AGENT_IMPORT_NOTES_KEY);
    return;
  }
  sessionStorage.setItem(AGENT_IMPORT_NOTES_KEY, JSON.stringify(notes));
}

export function takeAgentImportNotes(): string[] {
  if (typeof window === 'undefined') {
    return [];
  }
  const raw = sessionStorage.getItem(AGENT_IMPORT_NOTES_KEY);
  sessionStorage.removeItem(AGENT_IMPORT_NOTES_KEY);
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string') : [];
  } catch {
    return [];
  }
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function readBlobError(error: unknown, fallback: string): Promise<string> {
  const payload = error && typeof error === 'object' && 'payload' in error
    ? (error as { payload?: unknown }).payload
    : undefined;
  if (payload instanceof Blob) {
    try {
      const parsed = JSON.parse(await payload.text()) as { message?: string };
      if (parsed.message) {
        return parsed.message;
      }
    } catch {
      return fallback;
    }
  }
  if (error instanceof Error && error.message && !error.message.startsWith('Request failed')) {
    return error.message;
  }
  return fallback;
}
