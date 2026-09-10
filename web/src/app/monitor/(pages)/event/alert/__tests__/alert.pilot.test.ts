import { afterEach, describe, expect, it } from 'vitest';

import { mergePageContexts } from '@/components/ai-page-context/registry';
import { PAGE_CONTEXT_TEXT_BUDGET } from '@/components/ai-page-context/types';
import {
  buildAlertListCurrentTime,
  getMessage,
  getTextContext,
  readAlertListStamp,
} from '../alert.pilot';

const setAlertView = (search = '') => {
  window.history.replaceState({}, '', `/monitor/event/alert${search}`);
};

const alertListShell = (body: string, tab = 'activeAlarms') => `
  <div class="alert_alert_x">
    <div class="filters_filters_x">
      <span class="ant-tree-node-selected">主机</span>
    </div>
    <div class="alarmList_alarmList_x">
      <div class="ant-tabs-tab ant-tabs-tab-active" data-node-key="${tab}">活跃告警</div>
      <div class="ant-tabs-tab" data-node-key="historicalAlarms">历史告警</div>
      ${body}
    </div>
  </div>
`;

describe('alert.pilot gate', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setAlertView('');
  });

  it('does not produce a page snapshot on extra tabs', () => {
    setAlertView('?objId=all');
    document.body.innerHTML = `
      <div class="alarmList_alarmList_x">
        <div class="ant-tabs-tab ant-tabs-tab-active" data-node-key="related-topology">关联拓扑</div>
      </div>
    `;
    expect(getMessage().title).toBe('');
    expect(getTextContext().sections || []).toEqual([]);
  });

  it('uses tab and objId in title on host tabs', () => {
    setAlertView('?objId=12');
    document.body.innerHTML = alertListShell(`
      <div class="searchCondition_x">
        <div class="condition_x">
          <ul><li><span>级别</span></li></ul>
        </div>
      </div>
      <div class="table_table_x"><table></table></div>
    `);
    expect(getMessage().title).toBe('monitor-alert:activeAlarms:12');
  });
});

describe('alert.pilot fingerprint', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setAlertView('?objId=all');
  });

  it('changes currentTime when filters change, not when only refresh interval changes', () => {
    setAlertView('?objId=all');
    document.body.innerHTML = alertListShell(`
      <div class="searchCondition_x">
        <div class="condition_x">
          <ul>
            <li>
              <span>级别</span>
              <div class="ant-select"><span class="ant-select-selection-item">严重</span></div>
            </li>
          </ul>
          <div class="timeSelector_x">
            <div class="refreshBox_x"><div class="ant-select-selection-item">30秒</div></div>
          </div>
        </div>
      </div>
      <div class="table_table_x">
        <table>
          <thead><tr><th>级别</th><th>告警名称</th></tr></thead>
          <tbody class="ant-table-tbody">
            <tr class="ant-table-row"><td>严重</td><td>CPU 高</td></tr>
          </tbody>
        </table>
        <ul class="ant-pagination">
          <li class="ant-pagination-total-text">共 1 项</li>
          <li class="ant-pagination-item ant-pagination-item-1 ant-pagination-item-active">1</li>
        </ul>
      </div>
    `);
    const first = buildAlertListCurrentTime(readAlertListStamp());
    document.querySelector('.refreshBox_x .ant-select-selection-item')!.textContent = '1分钟';
    const intervalOnly = buildAlertListCurrentTime(readAlertListStamp());
    expect(intervalOnly).toBe(first);
    document.querySelector('.condition_x .ant-select-selection-item')!.textContent = '警告';
    const filterChanged = buildAlertListCurrentTime(readAlertListStamp());
    expect(filterChanged).not.toBe(first);
  });
});

describe('alert.pilot text context', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setAlertView('?objId=all');
  });

  it('includes identity, filters, page range, rendered rows, and skips action cells', () => {
    setAlertView('?objId=all');
    document.body.innerHTML = alertListShell(`
      <div class="searchCondition_x">
        <div class="condition_x">
          <ul>
            <li>
              <span>级别</span>
              <div class="ant-select">
                <span class="ant-select-selection-item"><span title="严重、警告">已选 2 项</span></span>
              </div>
            </li>
            <li>
              <span>状态</span>
              <div class="ant-select"><span class="ant-select-selection-item">活跃</span></div>
            </li>
          </ul>
        </div>
      </div>
      <div class="table_table_x">
        <input class="ant-input" value="CPU" />
        <table>
          <thead><tr><th>级别</th><th>告警名称</th><th>资产</th><th>操作</th></tr></thead>
          <tbody class="ant-table-tbody">
            <tr class="ant-table-row">
              <td>严重</td><td>CPU 高</td><td>host-a</td>
              <td><button class="ant-btn">详情</button><button class="ant-btn">关闭</button></td>
            </tr>
            <tr class="ant-table-row">
              <td>警告</td><td>磁盘高</td><td>host-b</td>
              <td><button class="ant-btn">详情</button></td>
            </tr>
          </tbody>
        </table>
        <ul class="ant-pagination">
          <li class="ant-pagination-total-text">共 40 项</li>
          <li class="ant-pagination-item ant-pagination-item-2 ant-pagination-item-active">2</li>
        </ul>
      </div>
    `);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('正在查看告警列表');
    expect(text).toContain('活跃告警');
    expect(text).toContain('主机');
    expect(text).toContain('严重');
    expect(text).toContain('警告');
    expect(text).toContain('活跃告警不按时间窗过滤');
    expect(text).toContain('CPU');
    expect(text).toContain('共 40 项');
    expect(text).toContain('当前第 2 页');
    expect(text).toContain('CPU 高');
    expect(text).toContain('host-a');
    expect(text).toContain('磁盘高');
    expect(text).not.toContain('详情');
    expect(text).not.toContain('关闭');
  });

  it('copies all currently rendered rows instead of capping at 10', () => {
    setAlertView('?objId=all');
    const rows = Array.from({ length: 20 }, (_, index) =>
      `<tr class="ant-table-row"><td>row-${index + 1}</td><td>host-${index + 1}</td></tr>`,
    ).join('');
    document.body.innerHTML = alertListShell(`
      <div class="searchCondition_x"><div class="condition_x"><ul></ul></div></div>
      <div class="table_table_x">
        <table>
          <thead><tr><th>告警名称</th><th>资产</th></tr></thead>
          <tbody class="ant-table-tbody">${rows}</tbody>
        </table>
      </div>
    `);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('row-1');
    expect(text).toContain('row-20');
  });

  it('keeps identity when table rows exceed the text budget', () => {
    const hugeRows = Array.from({ length: 20 }, (_, index) => `row-${index}:${'x'.repeat(500)}`).join('\n');
    const merged = mergePageContexts([{
      sections: [
        { id: 'alert-list-identity', label: '当前告警列表', content: '正在查看告警列表\n当前筛选: 级别: 严重', priority: 10 },
        { id: 'alert-detail-identity', label: '当前告警详情', content: '告警: CPU 高', priority: 10 },
        { id: 'alert-detail-events', label: '事件', content: '共 3 条，已附最近 3 条', priority: 8 },
        { id: 'alert-list-table', label: '当前页告警', content: hugeRows, priority: 4 },
      ],
    }]);
    const ids = (merged.sections || []).map((section) => section.id);
    expect(ids).toContain('alert-list-identity');
    expect(ids).toContain('alert-detail-identity');
    expect((merged.sections || []).reduce((sum, section) => sum + section.content.length, 0))
      .toBeLessThanOrEqual(PAGE_CONTEXT_TEXT_BUDGET);
  });

  it('does not treat a loading overlay as zero alerts', () => {
    setAlertView('?objId=all');
    document.body.innerHTML = alertListShell(`
      <div class="searchCondition_x"><div class="condition_x"><ul></ul></div></div>
      <div class="table_table_x">
        <div class="ant-spin ant-spin-spinning"></div>
        <table>
          <thead><tr><th>告警名称</th></tr></thead>
          <tbody class="ant-table-tbody">
            <tr class="ant-table-row"><td>旧告警</td></tr>
          </tbody>
        </table>
      </div>
    `);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('表格加载中');
    expect(text).not.toContain('旧告警');
  });

  it('reads historical time range from customSlect', () => {
    setAlertView('?objId=all');
    document.body.innerHTML = alertListShell(`
      <div class="searchCondition_x">
        <div class="condition_x">
          <ul></ul>
          <div class="customSlect_x">
            <div class="ant-select"><span class="ant-select-selection-item">最近7天</span></div>
          </div>
        </div>
      </div>
      <div class="table_table_x"><table></table></div>
    `, 'historicalAlarms');
    expect(getMessage().title).toBe('monitor-alert:historicalAlarms:all');
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('历史告警');
    expect(text).toContain('最近7天');
    expect(text).not.toContain('活跃告警不按时间窗过滤');
  });
});
