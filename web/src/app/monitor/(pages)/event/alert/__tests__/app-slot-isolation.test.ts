import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const pageSource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../page.tsx'),
  'utf8'
);

describe('monitor alert page app-slot isolation', () => {
  it('does not statically import alarm modules', () => {
    expect(pageSource).not.toMatch(/from ['"]@\/app\/alarm/);
  });

  it('does not host extra tabs from other apps', () => {
    expect(pageSource).not.toContain('useAppSlotTabs');
    expect(pageSource).not.toContain('monitor.event.extraTabs');
  });
});
