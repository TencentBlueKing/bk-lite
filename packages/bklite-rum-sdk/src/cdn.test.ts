// @vitest-environment jsdom
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const cdnBundle = resolve(import.meta.dirname, '../dist/bklite-rum-sdk.cdn.js');

describe('bklite-rum-sdk CDN facade', () => {
  it('exposes initCoreRum as a classic-script global', () => {
    const source = readFileSync(cdnBundle, 'utf8');
    expect(source.includes('\nexport {')).toBe(false);
    expect(source).toContain('initCoreRum');
    const previous = (globalThis as typeof globalThis & { initCoreRum?: unknown }).initCoreRum;
    try {
      new Function(source)();
      expect(typeof (globalThis as typeof globalThis & { initCoreRum?: unknown }).initCoreRum).toBe(
        'function',
      );
    } finally {
      (globalThis as typeof globalThis & { initCoreRum?: unknown }).initCoreRum = previous;
    }
  });

  it('replay entry registers the replay global hook', async () => {
    await import('../dist/bklite-rum-replay.js');
    expect(window.__coreRumReplay).toBeDefined();
    expect(typeof window.__coreRumReplay?.takeFullSnapshot).toBe('function');
  });

  it('enables inlineStylesheet so replay keeps page CSS under player CSP', () => {
    const source = readFileSync(resolve(import.meta.dirname, './cdn.ts'), 'utf8');
    expect(source).toMatch(/inlineStylesheet:\s*true/);
  });
});
