import { afterEach, describe, expect, it } from 'vitest';

import { readTreeLines, treeSection } from '../domSnapshot';
import { buildTableListContext } from '@/app/monitor/page-context/tableListContext';

describe('readTreeLines / treeSection', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('returns empty when there is no ant-tree', () => {
    document.body.innerHTML = '<span class="ant-tree-node-selected">主机</span>';
    expect(readTreeLines()).toEqual([]);
    expect(treeSection()).toEqual([]);
  });

  it('captures all visible nodes with counts and marks the selected one', () => {
    document.body.innerHTML = `
      <div class="ant-tree">
        <div class="ant-tree-treenode ant-tree-treenode-selected">
          <span class="ant-tree-node-content-wrapper ant-tree-node-selected">
            <span class="ant-tree-title">操作系统（2）</span>
          </span>
        </div>
        <div class="ant-tree-treenode">
          <span class="ant-tree-indent"><span class="ant-tree-indent-unit"></span></span>
          <span class="ant-tree-node-content-wrapper">
            <span class="ant-tree-title">数据库（22）</span>
          </span>
        </div>
        <div class="ant-tree-treenode">
          <span class="ant-tree-indent"><span class="ant-tree-indent-unit"></span></span>
          <span class="ant-tree-node-content-wrapper">
            <span class="ant-tree-title">
              <span class="treeMetaNode">
                <span class="icon_x"></span>
                <span class="label_x">中间件</span>
                <span class="count_x">22</span>
              </span>
            </span>
          </span>
        </div>
      </div>
    `;
    expect(readTreeLines()).toEqual([
      '操作系统（2） [当前]',
      '  数据库（22）',
      '  中间件 (22)',
    ]);
  });

  it('is included in buildTableListContext alongside the table', () => {
    document.body.innerHTML = `
      <div class="ant-tree">
        <div class="ant-tree-treenode ant-tree-treenode-selected">
          <span class="ant-tree-node-content-wrapper ant-tree-node-selected">
            <span class="ant-tree-title">操作系统（2）</span>
          </span>
        </div>
        <div class="ant-tree-treenode">
          <span class="ant-tree-node-content-wrapper">
            <span class="ant-tree-title">数据库（22）</span>
          </span>
        </div>
      </div>
      <div class="ant-table">
        <table>
          <thead><tr><th>对象名称</th></tr></thead>
          <tbody class="ant-table-tbody">
            <tr class="ant-table-row"><td>主机</td></tr>
          </tbody>
        </table>
      </div>
    `;
    const sections = buildTableListContext({ heading: '正在查看监控对象' }).sections || [];
    const tree = sections.find((section) => section.id === 'page-tree');
    expect(tree?.content).toContain('数据库（22）');
    expect(tree?.content).toContain('操作系统（2） [当前]');
    expect(sections.map((section) => section.content).join('\n')).toContain('主机');
  });
});
