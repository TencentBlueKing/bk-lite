import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

describe('monitor event workspace height contract', () => {
  it('passes remaining pane height through the monitor layout', () => {
    const source = readFileSync(resolve(root, 'layout.tsx'), 'utf8');
    expect(source).toMatch(/flex h-full min-h-0 w-full flex-1 flex-col/);
  });

  it('lets the strategy tree and table fill remaining height instead of hugging empty rows', () => {
    const source = readFileSync(
      resolve(root, 'event/strategy/page.tsx'),
      'utf8',
    );
    expect(source).toMatch(/wrapperClassName="flex h-full min-h-0/);
    expect(source).toMatch(/\[&>\.ant-spin-container\]:h-full/);
    expect(source).not.toMatch(/calc\(100vh/);
  });
});
