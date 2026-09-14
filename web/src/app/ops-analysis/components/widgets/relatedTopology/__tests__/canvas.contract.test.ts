import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const canvasSource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../canvas.tsx'),
  'utf8',
);

describe('related topology canvas scene widget', () => {
  it('does not query until an instUuid is bound and stays off share/report', () => {
    expect(canvasSource).toContain('config?.relatedTopology?.instUuid');
    expect(canvasSource).toContain("t('dashboard.relatedTopologySelectAsset')");
    expect(canvasSource).toContain('<RelatedTopology instUuid={instUuid} chartThemeMode={config?.chartThemeMode} />');
    expect(canvasSource).toContain('relatedTopologyCanvasStyle');
    expect(canvasSource).toContain('isScreenChartThemeMode(config?.chartThemeMode)');
    expect(canvasSource).toContain('shareSupported');
    expect(canvasSource).toContain("isSceneWidgetAllowedOnSurface('relatedTopology', surface)");
  });
});
