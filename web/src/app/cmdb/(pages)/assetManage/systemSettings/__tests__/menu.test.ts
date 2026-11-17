import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import path from 'node:path';

describe('cmdb system settings menu', () => {
  it('registers zh and en entries', () => {
    const raw = readFileSync(
      path.join(__dirname, '../../../../constants/menu.json'),
      'utf8'
    );
    const menu = JSON.parse(raw);
    const titles = (lang: 'zh' | 'en') =>
      JSON.stringify(menu[lang]).includes('/cmdb/assetManage/systemSettings');
    expect(titles('zh')).toBe(true);
    expect(titles('en')).toBe(true);
  });
});
