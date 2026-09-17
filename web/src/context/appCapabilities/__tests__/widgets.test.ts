import { describe, expect, it } from 'vitest';

import {
  APP_WIDGET_KEYS,
  appNameForWidgetKey,
  resolveWidgetLoader,
} from '../widgets';

describe('public widget keys', () => {
  it('declares the ten stable keys and maps them to sold apps', () => {
    expect([...APP_WIDGET_KEYS]).toEqual([
      'monitor.monitorView',
      'monitor.alertList',
      'monitor.monitorPolicy',
      'cmdb.baseInfo',
      'cmdb.assetChange',
      'ops-analysis.relatedTopology',
      'log.alertRawLog',
      'node.nodeStatus',
      'apm.serviceOverview',
      'apm.callChain',
    ]);
    expect(appNameForWidgetKey('monitor.monitorView')).toBe('monitor');
    expect(appNameForWidgetKey('monitor.alertList')).toBe('monitor');
    expect(appNameForWidgetKey('monitor.monitorPolicy')).toBe('monitor');
    expect(appNameForWidgetKey('cmdb.baseInfo')).toBe('cmdb');
    expect(appNameForWidgetKey('cmdb.assetChange')).toBe('cmdb');
    expect(appNameForWidgetKey('ops-analysis.relatedTopology')).toBe(
      'ops-analysis',
    );
    expect(appNameForWidgetKey('log.alertRawLog')).toBe('log');
    expect(appNameForWidgetKey('node.nodeStatus')).toBe('node');
    expect(appNameForWidgetKey('apm.serviceOverview')).toBe('apm');
    expect(appNameForWidgetKey('apm.callChain')).toBe('apm');
  });

  it('probes a declared loader by key without treating sibling keys as missing', () => {
    const loadRelated = () => Promise.resolve({ default: () => null });
    const api = {
      widgets: {
        'ops-analysis.relatedTopology': loadRelated,
      },
    };

    expect(resolveWidgetLoader(api, 'ops-analysis.relatedTopology')).toBe(
      loadRelated,
    );
    expect(resolveWidgetLoader(api, 'cmdb.baseInfo')).toBeNull();
  });

  it('treats an unauthorized or empty module as undeclared for every key', () => {
    expect(
      resolveWidgetLoader(null, 'ops-analysis.relatedTopology'),
    ).toBeNull();
    expect(resolveWidgetLoader({}, 'monitor.monitorView')).toBeNull();
    expect(
      resolveWidgetLoader(
        { widgets: { 'ops-analysis.relatedTopology': 'not-a-loader' } },
        'ops-analysis.relatedTopology',
      ),
    ).toBeNull();
  });
});
