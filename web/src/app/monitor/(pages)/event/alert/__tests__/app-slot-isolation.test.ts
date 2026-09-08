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

  it('renders extra tabs through the shared slot seam', () => {
    expect(pageSource).toContain('useAppSlotTabs(');
    expect(pageSource).toContain("'monitor.event.extraTabs'");
    expect(pageSource).toContain('id="monitor.event.extraTabs"');
  });
});
