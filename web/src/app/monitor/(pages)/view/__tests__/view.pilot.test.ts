import { afterEach, describe, expect, it } from 'vitest';

import { getTextContext, hiveColorHint, isHiveView, isMonitorViewIndexPath } from '../view.pilot';

describe('view.pilot pathname', () => {
  it('matches the view index and not dashboard or detail', () => {
    expect(isMonitorViewIndexPath('/monitor/view')).toBe(true);
    expect(isMonitorViewIndexPath('/monitor/view/')).toBe(true);
    expect(isMonitorViewIndexPath('/monitor/view/dashboard/host')).toBe(false);
    expect(isMonitorViewIndexPath('/monitor/view/detail')).toBe(false);
  });
});

describe('view.pilot tabs', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('list snapshot has current page rows and no hive cells', () => {
    document.body.innerHTML = `
      <div class="ant-tree">
        <div class="ant-tree-treenode ant-tree-treenode-selected">
          <span class="ant-tree-node-content-wrapper ant-tree-node-selected">
            <span class="ant-tree-title">主机</span>
          </span>
        </div>
        <div class="ant-tree-treenode">
          <span class="ant-tree-node-content-wrapper">
            <span class="ant-tree-title">Pod</span>
          </span>
        </div>
      </div>
      <div class="ant-segmented-item ant-segmented-item-selected"><input value="list" /></div>
      <div class="ant-table">
        <table>
          <thead><tr><th>实例</th><th>操作</th></tr></thead>
          <tbody class="ant-table-tbody">
            <tr class="ant-table-row"><td>host-a</td><td><button>详情</button></td></tr>
            <tr class="ant-table-row"><td>host-b</td><td><button>详情</button></td></tr>
          </tbody>
        </table>
        <ul class="ant-pagination">
          <li class="ant-pagination-total-text">共 40 项</li>
          <li class="ant-pagination-item ant-pagination-item-2 ant-pagination-item-active">2</li>
        </ul>
      </div>
    `;
    expect(isHiveView()).toBe(false);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('正在查看监控视图列表');
    expect(text).toContain('host-a');
    expect(text).toContain('当前第 2 页');
    expect(text).toContain('Pod');
    expect(text).toContain('主机 [当前]');
    expect(text).not.toContain('详情');
    expect(text).not.toContain('已加载格子');
  });

  it('hive snapshot has color and instance name, not list rows', () => {
    document.body.innerHTML = `
      <span class="ant-tree-node-selected">Pod</span>
      <div data-ai-hive-total="10" data-ai-hive-loaded="2" data-ai-hive-metric="Pod 阶段" data-ai-hive-node="">
        <div data-ai-hive-name="pay-pod" data-ai-hive-value="Failed" data-ai-hive-fill="#F43B2C"></div>
        <div data-ai-hive-name="ok-pod" data-ai-hive-value="Running" data-ai-hive-fill="#10e433"></div>
      </div>
      <div class="ant-table"><table><tbody class="ant-table-tbody"><tr class="ant-table-row"><td>should-not-appear</td></tr></tbody></table></div>
    `;
    expect(isHiveView()).toBe(true);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('正在查看监控视图蜂窝');
    expect(text).toContain('pay-pod');
    expect(text).toContain('红');
    expect(text).toContain('还有 8 个未加载');
    expect(text).not.toContain('should-not-appear');
  });

  it('maps reddish fills to 红', () => {
    expect(hiveColorHint('#F43B2C')).toContain('红');
  });
});
