import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const dir = dirname(fileURLToPath(import.meta.url));

function source(name: string) {
  return readFileSync(join(dir, '..', name), 'utf8');
}

describe('association action instance permission', () => {
  it('does not coerce missing row permission to empty deny', () => {
    const list = source('list.tsx');
    const picker = source('selectInstance.tsx');

    expect(list).not.toMatch(/instPermissions=\{record\.permission \|\| \[\]\}/);
    expect(picker).not.toMatch(/instPermissions=\{record\.permission \|\| \[\]\}/);
    expect(list).toMatch(/instPermissions=\{record\.permission\}/);
    expect(picker).toMatch(/instPermissions=\{record\.permission\}/);
  });

  it('keeps association actions on the asset-data menu path used by rack/room', () => {
    expect(source('list.tsx')).toMatch(
      /permissionPath=\{RACK_ROOM_ASSET_PERMISSION_PATH\}/,
    );
    expect(source('selectInstance.tsx')).toMatch(
      /permissionPath=\{RACK_ROOM_ASSET_PERMISSION_PATH\}/,
    );
  });
});
