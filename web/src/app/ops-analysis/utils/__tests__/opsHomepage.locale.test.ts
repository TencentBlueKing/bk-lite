import { describe, expect, it } from 'vitest';
import en from '@/app/ops-analysis/locales/en.json';
import zh from '@/app/ops-analysis/locales/zh.json';
import commonEn from '@/locales/en.json';
import commonZh from '@/locales/zh.json';

describe('opsHomepage success copy stays short', () => {
  it('uses one-line personal/default results without extra explanation', () => {
    expect(zh.opsHomepage.setPersonalSuccess).toBe('已设为个人首页');
    expect(zh.opsHomepage.clearPersonalSuccess).toBe('已设为默认首页');
    expect(zh.opsHomepage.setGlobalSuccess).toBe('已设为默认首页');
    expect(zh.opsHomepage.restoreGlobalSuccess).toBe('已取消默认首页');

    expect(en.opsHomepage.setPersonalSuccess).toBe('Set as personal homepage');
    expect(en.opsHomepage.clearPersonalSuccess).toBe('Set as default homepage');
    expect(en.opsHomepage.setGlobalSuccess).toBe('Set as default homepage');
    expect(en.opsHomepage.restoreGlobalSuccess).toBe('Default homepage unset');

    // Sidebar cancel-personal and switcher follow-default share the same short result.
    expect(zh.opsHomepage.clearPersonalSuccess).toBe(
      commonZh.common.homepageFollowGlobalSuccess,
    );
    expect(en.opsHomepage.clearPersonalSuccess).toBe(
      commonEn.common.homepageFollowGlobalSuccess,
    );

    expect(zh.opsHomepage.clearPersonalSuccess).not.toMatch(/下次登录|若默认/);
    expect(en.opsHomepage.clearPersonalSuccess).not.toMatch(/next login|If that is still/i);
    expect(zh.opsHomepage.restoreGlobalSuccess).not.toMatch(/恢复为工作台/);
    expect(en.opsHomepage.restoreGlobalSuccess).not.toMatch(/Restored to the workbench/i);
  });
});
