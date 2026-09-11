import { afterEach, describe, expect, it } from 'vitest';

import { getMessage, getTextContext } from '../incidents.pilot';

const setIncidentView = (pathname = '/alarm/incidents') => {
  window.history.replaceState({}, '', pathname);
};

const incidentListShell = (body: string) => `
  <div class="container_container_x">
    <div class="filters_filters_x">
      <h3>过滤项</h3>
      <div class="item_x">
        <div class="collapse-title"><span class="title">级别</span></div>
        <div class="header_x"><span>级别</span></div>
        <label class="ant-checkbox-wrapper ant-checkbox-wrapper-checked">致命</label>
      </div>
    </div>
    <div class="content_content_x">
      <input class="ant-input" value="调度失败" />
      ${body}
    </div>
  </div>
`;

describe('incidents.pilot gate', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setIncidentView('/alarm/incidents');
  });

  it('does not collect the list snapshot on incident detail', () => {
    setIncidentView('/alarm/incidents/detail?id=1');
    document.body.innerHTML = incidentListShell(`
      <div class="ant-pagination-total-text">共 3 条</div>
      <table>
        <thead><tr><th>事故名称</th><th>操作</th></tr></thead>
        <tbody><tr class="ant-table-row"><td>旧事故</td><td><button>详情</button></td></tr></tbody>
      </table>
    `);
    expect(getMessage().title).toBe('');
    expect(getTextContext().sections || []).toEqual([]);
  });

  it('collects identity, filters, and current rows on the list page', () => {
    setIncidentView('/alarm/incidents');
    document.body.innerHTML = incidentListShell(`
      <div class="ant-pagination-total-text">共 3 条</div>
      <li class="ant-pagination-item ant-pagination-item-active">1</li>
      <table>
        <thead><tr><th>级别</th><th>事故名称</th><th>操作</th></tr></thead>
        <tbody>
          <tr class="ant-table-row"><td>致命</td><td>节点不可用</td><td><button>详情</button></td></tr>
        </tbody>
      </table>
    `);
    expect(getMessage().title).toBe('alarm-incident:list');
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('正在查看事故列表');
    expect(text).toContain('级别: 致命');
    expect(text).toContain('搜索: 调度失败');
    expect(text).toContain('节点不可用');
    expect(text).not.toContain('详情');
  });
});
