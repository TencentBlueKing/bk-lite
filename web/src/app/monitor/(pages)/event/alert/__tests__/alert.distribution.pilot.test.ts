import { afterEach, describe, expect, it } from 'vitest';

import type { PageContextToolkit } from '@/components/ai-page-context/types';
import { getContext, getTextContext } from '../alert.pilot';

const setAlertView = (search = '') => {
  window.history.replaceState({}, '', `/monitor/event/alert${search}`);
};

const alertListShell = (body: string, extra = '') => `
  <div class="alert_alert_x">
    <div class="alarmList_alarmList_x">
      <div class="ant-tabs-tab ant-tabs-tab-active" data-node-key="activeAlarms">活跃告警</div>
      ${extra}
      ${body}
    </div>
  </div>
`;

describe('alert.pilot distribution chart', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setAlertView('');
  });

  const toolkit = (images: Array<{ caption: string; dataUrl: string }>): PageContextToolkit => ({
    captureEchartsFromDoms: async () => [],
    captureEchartsFromDom: async () => [],
    captionFromOption: () => '',
    captureRechartsFromDoms: async () => images,
  });

  it('captures one image when the distribution collapse is open', async () => {
    setAlertView('?objId=all');
    document.body.innerHTML = alertListShell(`
      <div class="chartWrapper_x">
        <div class="collapse-title"><span class="title">告警级别分布</span></div>
        <div class="collapse-content">
          <div class="chart_x"><div class="recharts-wrapper"><svg></svg></div></div>
        </div>
      </div>
      <div class="table_table_x">
        <table>
          <thead><tr><th>告警名称</th></tr></thead>
          <tbody class="ant-table-tbody"><tr class="ant-table-row"><td>CPU 高</td></tr></tbody>
        </table>
        <ul class="ant-pagination">
          <li class="ant-pagination-item ant-pagination-item-1 ant-pagination-item-active">1</li>
        </ul>
      </div>
    `);
    const full = await getContext(toolkit([{ caption: '告警级别分布', dataUrl: 'data:image/jpeg,x' }]));
    expect(full.images).toHaveLength(1);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('CPU 高');
    expect(text).toContain('当前第 1 页');
  });

  it('does not capture when the distribution chart is collapsed', async () => {
    setAlertView('?objId=all');
    document.body.innerHTML = alertListShell(`
      <div class="chartWrapper_x">
        <div class="collapse-title"><span class="title">告警级别分布</span></div>
      </div>
      <div class="table_table_x"><table></table></div>
    `);
    const full = await getContext(toolkit([{ caption: '告警级别分布', dataUrl: 'data:image/jpeg,x' }]));
    expect(full.images || []).toEqual([]);
  });
});
