export const MAX_SSE_LEFTOVER_BYTES = 64 * 1024;

export interface SseLogStreamState {
  leftover: string;
}

export function createSseLogStreamState(): SseLogStreamState {
  return { leftover: '' };
}

export function parseSseLogChunk(
  chunk: string,
  state: SseLogStreamState
): string[] {
  const messages: string[] = [];
  let buffer = `${state.leftover}${chunk}`;

  while (true) {
    const separator = buffer.match(/\r?\n\r?\n/);
    if (!separator || separator.index === undefined) {
      break;
    }
    const frame = buffer.slice(0, separator.index);
    buffer = buffer.slice(separator.index + separator[0].length);
    const message = extractMessageFromFrame(frame);
    if (message !== null) {
      messages.push(message);
    }
  }

  state.leftover =
    buffer.length > MAX_SSE_LEFTOVER_BYTES ? '' : buffer;
  return messages;
}

function extractMessageFromFrame(frame: string): string | null {
  const dataParts: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith(':') || !line.startsWith('data:')) {
      continue;
    }
    const rawValue = line.slice(5);
    dataParts.push(rawValue.startsWith(' ') ? rawValue.slice(1) : rawValue);
  }
  if (!dataParts.length) {
    return null;
  }
  const payload = dataParts.join('\n');
  try {
    const parsed: unknown = JSON.parse(payload);
    if (parsed && typeof parsed === 'object') {
      const record = parsed as Record<string, unknown>;
      if (typeof record.message === 'string') {
        return record.message;
      }
      if (typeof record._msg === 'string') {
        return record._msg;
      }
    }
  } catch {
    return null;
  }
  return payload;
}
