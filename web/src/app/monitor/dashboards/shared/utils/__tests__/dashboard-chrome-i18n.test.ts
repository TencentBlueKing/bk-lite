import { describe, expect, it } from 'vitest';

import { DASHBOARD_TEXT_IDS } from '../dashboard-text-map.generated';
import { FLOW_VIEW_LABELS } from '../flow-view-navigation';
import { localizeDashboardReturnLabel, tDashboardText } from '../content-i18n';

const translate = (
  id: string,
  defaultMessage?: string,
  values?: Record<string, string>
) => {
  const template = {
    'monitor.dashboards.text.genericSNMP': 'Generic SNMP',
    'monitor.dashboards.text.snmpMonitoring': 'SNMP Monitoring',
    'monitor.dashboards.text.netflowTraffic': 'NetFlow Traffic',
    'monitor.dashboards.text.sflowTraffic': 'sFlow Traffic',
    'monitor.dashboards.text.trafficTrend': 'Traffic Trends',
    'monitor.dashboards.text.backToMonitorView': 'Back to Monitor View',
    'monitor.dashboards.common.backToObjectViewList': 'Back to {objectName} View',
    'monitor.dashboards.common.backToObjectIntegrationAssets':
      'Back to {objectName} Integration Assets',
  }[id] || defaultMessage || id;
  return template.replace(/\{(\w+)\}/g, (_, key) => values?.[key] ?? `{${key}}`);
};

describe('dashboard chrome i18n', () => {
  it('maps monitor template, protocol groups, and traffic section copy', () => {
    expect(DASHBOARD_TEXT_IDS['通用 SNMP']).toBe('genericSNMP');
    expect(DASHBOARD_TEXT_IDS['流量趋势']).toBe('trafficTrend');
    expect(FLOW_VIEW_LABELS.snmp).toBe('SNMP 监控');
    expect(FLOW_VIEW_LABELS.netflow).toBe('NetFlow 流量');
    expect(FLOW_VIEW_LABELS.sflow).toBe('sFlow 流量');
    for (const label of Object.values(FLOW_VIEW_LABELS)) {
      expect(DASHBOARD_TEXT_IDS[label]).toBeTruthy();
      expect(tDashboardText(translate, label)).not.toBe(label);
    }
    expect(tDashboardText(translate, '通用 SNMP')).toBe('Generic SNMP');
    expect(tDashboardText(translate, '流量趋势')).toBe('Traffic Trends');
  });

  it('translates return labels that include the object name', () => {
    const params = new URLSearchParams({
      return_object_id: '16',
      return_object_name: 'Switch',
    });
    expect(localizeDashboardReturnLabel(translate, params)).toBe('Back to Switch View');

    params.set('return_source', 'integration');
    expect(localizeDashboardReturnLabel(translate, params)).toBe(
      'Back to Switch Integration Assets'
    );

    expect(
      localizeDashboardReturnLabel(translate, new URLSearchParams())
    ).toBe('Back to Monitor View');
  });
});
