import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { ROOM3D_EMBED_API_PATH } from '@/app/ops-analysis/api/room3D';

const embedSource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../embed.tsx'),
  'utf8',
);

describe('room3D public embed', () => {
  it('queries a single room by instUuid through the ops-analysis widget API', () => {
    expect(ROOM3D_EMBED_API_PATH).toBe(
      '/operation_analysis/api/scene_widgets/room3d/',
    );
    expect(embedSource).toContain('getRoom3DLayout');
    expect(embedSource).toContain('instUuid');
    expect(embedSource).not.toContain('application3D');
    expect(embedSource).not.toContain('wall');
  });
});
