/**
 * Incremental SSE text parser with incomplete-line buffering.
 * Shared by SSEHandler and the UI stream reader.
 */
export class SSEStreamParser {
  private buffer = '';

  /**
   * Feed a decoded text chunk and return complete `data:` payloads.
   * JSON payloads are parsed; non-JSON data strings are returned as-is.
   */
  public push(chunk: string): unknown[] {
    this.buffer += chunk;
    const lines = this.buffer.split('\n');
    this.buffer = lines[lines.length - 1] ?? '';

    const payloads: unknown[] = [];
    for (let i = 0; i < lines.length - 1; i++) {
      const line = lines[i].trim();
      if (!line || line.startsWith(':')) {
        continue;
      }

      const data = line.startsWith('data: ') ? line.slice(6) : line;
      if (!data.trim()) {
        continue;
      }

      try {
        payloads.push(JSON.parse(data));
      } catch {
        payloads.push(data);
      }
    }

    return payloads;
  }

  /** Drop any buffered partial line. */
  public reset(): void {
    this.buffer = '';
  }
}
