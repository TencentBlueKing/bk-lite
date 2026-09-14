import { afterEach, describe, expect, it } from 'vitest';

import {
  buildAlarmCenterCurrentTime,
  getMessage,
  getTextContext,
  readAlarmCenterListStamp,
} from '../alarms.pilot';

const setAlarmView = (pathname = '/alarm/alarms') => {
  window.history.replaceState({}, '', pathname);
};

const alarmListShell = (body: string, tab = 'activeAlarms') => `
  <div class="alert_alert_x">
    <div class="filters_filters_x">
      <h3>过滤项</h3>
      <div class="item_x">
        <div class="collapse-title"><span class="title">级别</span></div>
        <div class="header_x"><span>级别</span></div>
        <label class="ant-checkbox-wrapper ant-checkbox-wrapper-checked">预警</label>
      </div>
      <div class="item_x">
        <div class="collapse-title"><span class="title">状态</span></div>
        <div class="header_x"><span>状态</span></div>
        <label class="ant-checkbox-wrapper ant-checkbox-wrapper-checked">待响应</label>
      </div>
    </div>
    <div class="alertContent_alertContent_x">
      <div class="chartWrapper_x">
        <div class="customSlect_x">
          <div class="refreshBox_x"><div class="ant-select-selection-item">30秒</div></div>
        </div>
      </div>
      <div class="table_table_x">
        <div class="ant-tabs-tab ant-tabs-tab-active" data-node-key="${tab}">活跃告警</div>
        <div class="ant-tabs-tab" data-node-key="historicalAlarms">所有告警</div>
        ${body}
      </div>
    </div>
  </div>
`;

describe('alarms.pilot gate', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setAlarmView('/alarm/alarms');
  });

  it('does not produce a page snapshot on other alarm routes', () => {
    setAlarmView('/alarm/integration');
    document.body.innerHTML = alarmListShell('<table></table>');
    expect(getMessage().title).toBe('');
    expect(getTextContext().sections || []).toEqual([]);
  });

  it('uses the active tab in title', () => {
    setAlarmView('/alarm/alarms');
    document.body.innerHTML = alarmListShell('<table></table>', 'historicalAlarms');
    expect(getMessage().title).toBe('alarm-center:historicalAlarms');
  });
});

describe('alarms.pilot fingerprint', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setAlarmView('/alarm/alarms');
  });

  it('changes currentTime when filters change, not when only refresh interval changes', () => {
    setAlarmView('/alarm/alarms');
    document.body.innerHTML = alarmListShell(`
      <div class="ant-pagination-total-text">共 2 条</div>
      <li class="ant-pagination-item ant-pagination-item-active">1</li>
      <table>
        <thead><tr><th>级别</th><th>告警名称</th><th>操作</th></tr></thead>
        <tbody><tr class="ant-table-row"><td>预警</td><td>CPU 高</td><td><button>详情</button></td></tr></tbody>
      </table>
    `);
    const first = buildAlarmCenterCurrentTime(readAlarmCenterListStamp());
    document.querySelector('.refreshBox_x .ant-select-selection-item')!.textContent = '1分钟';
    const afterRefresh = buildAlarmCenterCurrentTime(readAlarmCenterListStamp());
    expect(afterRefresh).toBe(first);
    document.querySelector('.ant-checkbox-wrapper-checked')!.textContent = '致命';
    const afterFilter = buildAlarmCenterCurrentTime(readAlarmCenterListStamp());
    expect(afterFilter).not.toBe(first);
  });
});

describe('alarms.pilot text context', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setAlarmView('/alarm/alarms');
  });

  it('includes identity, filters, page range, rendered rows, and skips action cells', () => {
    setAlarmView('/alarm/alarms');
    document.body.innerHTML = alarmListShell(`
      <label class="ant-checkbox-wrapper ant-checkbox-wrapper-checked">我的告警</label>
      <div class="ant-pagination-total-text">共 2 条</div>
      <li class="ant-pagination-item ant-pagination-item-active">1</li>
      <table>
        <thead><tr><th>级别</th><th>告警名称</th><th>操作</th></tr></thead>
        <tbody>
          <tr class="ant-table-row"><td>预警</td><td>FailedScheduling</td><td><button>详情</button></td></tr>
          <tr class="ant-table-row"><td>预警</td><td>BackOff</td><td><button>详情</button></td></tr>
        </tbody>
      </table>
    `);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('正在查看告警中心列表');
    expect(text).toContain('视图: 活跃告警');
    expect(text).toContain('级别: 预警');
    expect(text).toContain('活跃告警不按时间窗过滤');
    expect(text).toContain('共 2 条');
    expect(text).toContain('FailedScheduling');
    expect(text).not.toContain('详情');
  });

  it('reads historical time range from customSlect', () => {
    setAlarmView('/alarm/alarms');
    document.body.innerHTML = alarmListShell(`
      <table><thead><tr><th>级别</th></tr></thead><tbody></tbody></table>
    `, 'historicalAlarms');
    const range = document.querySelector('[class*="customSlect"]')!;
    range.insertAdjacentHTML('afterbegin', '<span class="ant-select-selection-item">近 7 天</span>');
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('视图: 所有告警');
    expect(text).toContain('时间筛选: 近 7 天');
  });

  it('does not treat a loading overlay as zero alerts', () => {
    setAlarmView('/alarm/alarms');
    document.body.innerHTML = alarmListShell(`
      <div class="ant-spin-spinning"></div>
      <div class="ant-pagination-total-text">共 8 条</div>
      <table>
        <thead><tr><th>级别</th></tr></thead>
        <tbody><tr class="ant-table-row"><td>旧行</td></tr></tbody>
      </table>
    `);
    const text = (getTextContext().sections || []).map((section) => `${section.id}\n${section.content}`).join('\n');
    expect(text).toContain('表格加载中');
    expect(text).not.toContain('alarm-center-list-table');
  });
});
