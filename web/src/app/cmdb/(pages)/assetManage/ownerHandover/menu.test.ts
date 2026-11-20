import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import path from 'node:path';

describe('cmdb owner handover menu', () => {
  it('registers zh and en entries under management', () => {
    const raw = readFileSync(path.join(__dirname, '../../../constants/menu.json'), 'utf8');
    const menu = JSON.parse(raw);
    for (const lang of ['zh', 'en'] as const) {
      const management = menu[lang].find(
        (entry: { name?: string }) => entry.name === 'Management'
      );
      const item = management?.children?.find(
        (entry: { url?: string }) => entry.url === '/cmdb/assetManage/ownerHandover'
      );
      expect(item?.name).toBe('model_management');
      expect(item?.title).toBe(lang === 'zh' ? '负责人交接' : 'Owner Handover');
    }
  });
});
