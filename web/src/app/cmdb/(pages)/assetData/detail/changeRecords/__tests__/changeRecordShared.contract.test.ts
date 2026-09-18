import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string) {
  return readFileSync(resolve(here, relativePath), 'utf8');
}

describe('change record shared presentation', () => {
  const pageSource = readSource('../page.tsx');
  const styleSource = readSource('../index.module.scss');
  const timelineSource = readSource('../ChangeRecordTimeline.tsx');
  const detailSource = readSource('../ChangeRecordDetail.tsx');

  it('lets the main page keep filters, stats, export and the viewport split layout', () => {
    expect(pageSource).toContain("from './ChangeRecordTimeline'");
    expect(pageSource).toContain("from './ChangeRecordDetail'");
    expect(pageSource).toContain('exportChangeRecords');
    expect(pageSource).toContain('styles.statsBar');
    expect(pageSource).toContain('styles.filterChips');
    expect(pageSource).toContain('styles.changeRecords');
    expect(pageSource).not.toContain('styles.embedded');
    expect(pageSource).toContain('styles.timelineCol');
    expect(pageSource).toContain('styles.detailCol');
    expect(styleSource).toContain('calc(100vh - 140px)');
  });

  it('reuses the same timeline and field/relation diff views in the shared components', () => {
    expect(timelineSource).toContain('styles.timelineItem');
    expect(timelineSource).toContain('styles.timelineDot');
    expect(timelineSource).toContain('ChangeRecordScenarioTag');
    expect(timelineSource).toContain("convertToLocalizedTime(item.created_at, 'MM-DD HH:mm')");
    expect(detailSource).toContain('attr_diff');
    expect(detailSource).toContain('relation_diff');
    expect(detailSource).toContain('TableFieldDiffView');
    expect(detailSource).toContain('noChangeContent');
    expect(detailSource).not.toContain('onBack');
    expect(detailSource).not.toContain('backToTimeline');
    expect(pageSource).toContain('onPrev');
    expect(pageSource).toContain('onNext');
    expect(pageSource).toContain('onClose');
  });

  it('keeps change snapshots typed without any', () => {
    const typesSource = readSource('../changeRecordTypes.ts');
    expect(typesSource).toContain('before_data?: Record<string, unknown>');
    expect(typesSource).toContain('after_data?: Record<string, unknown>');
    expect(typesSource).not.toMatch(/Record<string,\s*any>/);
  });
});
