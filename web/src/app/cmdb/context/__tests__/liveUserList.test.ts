import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const testDir = dirname(fileURLToPath(import.meta.url));
const cmdbRoot = resolve(testDir, '../..');

const SNAPSHOT_USER_LIST = /useRef\(\s*(?:common(?:Context)?|commonContext)\?\.userList/;

const collectTsxFiles = (dir: string): string[] => {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === '__tests__') continue;
    const full = join(dir, name);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      out.push(...collectTsxFiles(full));
      continue;
    }
    if (name.endsWith('.ts') || name.endsWith('.tsx')) {
      out.push(full);
    }
  }
  return out;
};

describe('CMDB user field options stay live after users load', () => {
  it('does not freeze userList with useRef on first render', () => {
    const offenders = collectTsxFiles(cmdbRoot)
      .filter((file) => SNAPSHOT_USER_LIST.test(readFileSync(file, 'utf8')))
      .map((file) => relative(cmdbRoot, file));

    expect(offenders).toEqual([]);
  });

  it('reads userList from CommonContext without snapshotting', () => {
    const source = readFileSync(resolve(testDir, '../common.tsx'), 'utf8');
    expect(source).toMatch(/export const useCmdbUserList/);
    expect(source).toMatch(/useCommon\(\)\?\.userList/);
    expect(source).not.toMatch(/useRef\([\s\S]*userList/);
  });
});
