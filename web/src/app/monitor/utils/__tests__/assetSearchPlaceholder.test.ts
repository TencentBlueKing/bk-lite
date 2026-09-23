import { describe, expect, it } from 'vitest';
import { ObjectItem } from '@/app/monitor/types';
import { getAssetSearchPlaceholderKey } from '@/app/monitor/utils/assetSearchPlaceholder';

const object = (overrides: Partial<ObjectItem> & Pick<ObjectItem, 'name'>): ObjectItem =>
  ({ id: 1, type: 'OS', ...overrides }) as ObjectItem;

describe('getAssetSearchPlaceholderKey', () => {
  it('uses name and IP for ordinary objects', () => {
    expect(getAssetSearchPlaceholderKey(object({ name: 'Host' }))).toBe(
      'monitor.views.searchPlaceholderDefault'
    );
    expect(
      getAssetSearchPlaceholderKey(
        object({
          name: 'Mysql',
          instance_summary_columns: [{ fact: 'asset.ip', title: 'monitor.views.assetIp' }]
        })
      )
    ).toBe('monitor.views.searchPlaceholderDefault');
  });

  it('adds probe node and target for probe objects', () => {
    expect(
      getAssetSearchPlaceholderKey(
        object({
          name: 'Website',
          instance_summary_columns: [
            { fact: 'collector.nodes', title: 'monitor.views.probeNodes' },
            { fact: 'probe.target', title: 'monitor.views.probeTarget' }
          ]
        })
      )
    ).toBe('monitor.views.searchPlaceholderProbe');
    expect(getAssetSearchPlaceholderKey(object({ name: 'Ping' }))).toBe(
      'monitor.views.searchPlaceholderProbe'
    );
    expect(getAssetSearchPlaceholderKey(object({ name: 'TCPPort' }))).toBe(
      'monitor.views.searchPlaceholderProbe'
    );
  });

  it('adds process name, host name and host IP for Process', () => {
    expect(getAssetSearchPlaceholderKey(object({ name: 'Process' }))).toBe(
      'monitor.views.searchPlaceholderProcess'
    );
  });
});
