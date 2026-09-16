import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const webSrc = resolve(root, '../../../..');

const read = (...segments: string[]) =>
  readFileSync(resolve(...segments), 'utf8');

const workspacePages = [
  ['list', read(root, 'list/page.tsx')],
  ['object', read(root, 'object/page.tsx')],
  ['group', read(root, 'group/page.tsx')],
] as const;

describe('monitor integration workspace spacing contract', () => {
  it.each(workspacePages)(
    '%s uses the shared tree workspace gutters',
    (_name, source) => {
      expect(source).toMatch(
        /flex h-full min-h-0 w-full min-w-0 gap-2\.5 overflow-hidden/,
      );
      expect(source).toMatch(/px-2\.5 py-5/);
      expect(source).toMatch(
        /flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-\[var\(--color-bg-1\)\] p-5/,
      );
      expect(source).toMatch(/mb-4 flex min-w-0 shrink-0/);
      expect(source).not.toMatch(/calc\(100vh/);
    },
  );

  it('keeps the asset page on the same 10/20/16 gutters', () => {
    const source = read(root, 'asset/index.module.scss');
    expect(source).toMatch(/gap:\s*10px;/);
    expect(source).toMatch(/padding:\s*20px 10px;/);
    expect(source).toMatch(/padding:\s*20px;/);
    expect(source).toMatch(/margin-bottom:\s*16px;/);
  });

  it('keeps TreeWorkspaceShell defaults aligned with the four pages', () => {
    const source = read(
      webSrc,
      'components/tree-workspace-shell/index.tsx',
    );
    expect(source).toMatch(
      /containerClassName = 'flex h-full min-h-0 w-full min-w-0 gap-2\.5 overflow-hidden'/,
    );
    expect(source).toMatch(/px-2\.5 py-5/);
    expect(source).toMatch(/p-5/);
    expect(source).not.toMatch(/calc\(100vh/);
  });
});
