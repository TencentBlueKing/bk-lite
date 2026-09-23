import { readFile, stat } from 'node:fs/promises';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('bklite-rum-sdk distribution', () => {
  it('keeps the optional Replay recorder out of the transport bundle', async () => {
    const output = resolve(import.meta.dirname, '../dist/index.js');
    const [source, info] = await Promise.all([
      readFile(output, 'utf8'),
      stat(output),
    ]);
    expect(source).toContain('faro.session_recording.event');
    expect(source).not.toContain('recordDOM');
    expect(source).not.toContain('stylesheetManager');
    expect(info.size).toBeLessThan(100_000);
  });
});
