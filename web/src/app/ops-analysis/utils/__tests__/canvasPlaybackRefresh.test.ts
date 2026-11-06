import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { canvasPeriodicRefreshEnabled } from '@/app/ops-analysis/utils/canvasPlaybackRefresh';

const PAGES = [
  'src/app/ops-analysis/(pages)/view/dashBoard/index.tsx',
  'src/app/ops-analysis/(pages)/view/topology/index.tsx',
  'src/app/ops-analysis/(pages)/view/architecture/index.tsx',
  'src/app/ops-analysis/(pages)/view/screen/index.tsx',
  'src/app/ops-analysis/(pages)/view/report/index.tsx',
  'src/app/ops-analysis/(pages)/view/networkTopology/index.tsx',
];

describe('canvas playback refresh', () => {
  it('turns periodic refresh off only while playback is on', () => {
    expect(canvasPeriodicRefreshEnabled(true, true)).toBe(false);
    expect(canvasPeriodicRefreshEnabled(false, true)).toBe(false);
    expect(canvasPeriodicRefreshEnabled(true, false)).toBe(true);
    expect(canvasPeriodicRefreshEnabled(false, false)).toBe(false);
  });

  it('gates every canvas periodic refresh and keeps architecture playback on a single status fetch', () => {
    for (const page of PAGES) {
      const source = readFileSync(resolve(process.cwd(), page), 'utf8');
      expect(source).toContain('canvasPeriodicRefreshEnabled(');
    }
    const architecture = readFileSync(
      resolve(process.cwd(), 'src/app/ops-analysis/(pages)/view/architecture/index.tsx'),
      'utf8',
    );
    expect(architecture).toMatch(/architectureStatusRequestMode\(\{[^}]*playbackMode/s);
  });
});
