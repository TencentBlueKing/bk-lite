import { describe, expect, it } from 'vitest';

import { formatMonitorViewPluginTabs } from '../monitorViewPlugins';

describe('formatMonitorViewPluginTabs', () => {
  it('uses plugin id as tab value so metrics catalog can accept it', () => {
    expect(
      formatMonitorViewPluginTabs([
        { id: 7, name: 'Host', display_name: '主机' },
      ]),
    ).toEqual([{ label: '主机', value: '7' }]);
  });

  it('drops plugins without a numeric id', () => {
    expect(
      formatMonitorViewPluginTabs([
        { name: 'Host', display_name: '主机' },
        { id: 12, name: 'Host', display_name: '主机' },
      ]),
    ).toEqual([{ label: '主机', value: '12' }]);
  });

  it('keeps builtin plugins first, matching the monitor-center tab order', () => {
    expect(
      formatMonitorViewPluginTabs([
        { id: 3, name: 'custom', display_name: '自定义', is_custom: true },
        { id: 1, name: 'Host', display_name: '主机', is_pre: true },
        { id: 2, name: 'other', display_name: '其他' },
      ]),
    ).toEqual([
      { label: '主机', value: '1' },
      { label: '其他', value: '2' },
      { label: '自定义', value: '3' },
    ]);
  });
});
