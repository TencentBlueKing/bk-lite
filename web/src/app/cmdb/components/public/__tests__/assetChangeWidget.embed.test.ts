import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const widgetSource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../AssetChangeWidget.tsx'),
  'utf8',
);

describe('cmdb.assetChange public widget', () => {
  it('embeds the shared change-record timeline and detail, not a message-card list or the full page', () => {
    expect(widgetSource).toContain('ChangeRecordTimeline');
    expect(widgetSource).toContain('ChangeRecordDetail');
    expect(widgetSource).toContain("from '@/app/cmdb/(pages)/assetData/detail/changeRecords/ChangeRecordTimeline'");
    expect(widgetSource).toContain("from '@/app/cmdb/(pages)/assetData/detail/changeRecords/ChangeRecordDetail'");
    expect(widgetSource).not.toContain('changeRecords/page');
    expect(widgetSource).not.toContain('rounded-md border border-[var(--color-border-2)] px-3 py-2');
    expect(widgetSource).not.toContain('exportChangeRecords');
    expect(widgetSource).not.toContain('styles.statsBar');
    expect(widgetSource).not.toContain('styles.filterChips');
    expect(widgetSource).not.toContain('useSearchParams');
    expect(widgetSource).not.toContain('useCommon');
  });

  it('bootstraps model_id from instance detail, keeps the CMDB open link, and fills the host instead of 100vh', () => {
    expect(widgetSource).toContain('getInstanceDetail');
    expect(widgetSource).toContain('getChangeRecords');
    expect(widgetSource).toContain("t('Model.openInCmdb')");
    expect(widgetSource).toContain('/cmdb/assetData/detail/changeRecords');
    expect(widgetSource).toContain('inst_uuid');
    expect(widgetSource).toContain('model_id');
    expect(widgetSource).toContain('styles.embedded');
    expect(widgetSource).toContain('h-full');
    expect(widgetSource).not.toContain('100vh');
    expect(widgetSource).toContain('DEFAULT_SCENARIOS');
  });

  it('shows a full-height timeline first and opens detail as a second step with an explicit back control', () => {
    expect(widgetSource).toContain("useState<'list' | 'detail'>");
    expect(widgetSource).toContain("setPane('detail')");
    expect(widgetSource).toContain("setPane('list')");
    expect(widgetSource).toContain("pane === 'list'");
    expect(widgetSource).toContain("pane === 'detail'");
    expect(widgetSource).toContain("t('Model.changeRecord.backToTimeline')");
    expect(widgetSource).toContain('LeftOutlined');
    expect(widgetSource).toContain('AssetChangeDetailToolbar');
    expect(widgetSource).toContain('objectSwitcher');
    expect(widgetSource).toContain('onEmbedToolbar');
    expect(widgetSource).toContain('min-w-0 flex-1');
    expect(widgetSource).not.toContain('headerExtra');
    expect(widgetSource).not.toContain('onBack={');
    expect(widgetSource).not.toContain("t('common.back')");
    expect(widgetSource).not.toContain('message-card');
  });
});
