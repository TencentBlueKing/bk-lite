import { describe, expect, it } from 'vitest';

import {
  APP_WIDGET_KEYS,
  appNameForWidgetKey,
  resolveWidgetLoader,
} from '../widgets';

describe('public widget keys', () => {
  it('declares the six stable keys and maps them to sold apps', () => {
    expect([...APP_WIDGET_KEYS]).toEqual([
      'monitor.monitorView',
      'monitor.alertList',
      'cmdb.baseInfo',
      'ops-analysis.relatedTopology',
      'ops-analysis.networkStatusTopology',
      'ops-analysis.application3D',
    ]);
    expect(appNameForWidgetKey('monitor.monitorView')).toBe('monitor');
    expect(appNameForWidgetKey('monitor.alertList')).toBe('monitor');
    expect(appNameForWidgetKey('cmdb.baseInfo')).toBe('cmdb');
    expect(appNameForWidgetKey('ops-analysis.relatedTopology')).toBe(
      'ops-analysis',
    );
    expect(appNameForWidgetKey('ops-analysis.networkStatusTopology')).toBe(
      'ops-analysis',
    );
    expect(appNameForWidgetKey('ops-analysis.application3D')).toBe(
      'ops-analysis',
    );
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
    expect(
      resolveWidgetLoader(api, 'ops-analysis.networkStatusTopology'),
    ).toBeNull();
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
