import { afterEach, describe, expect, it } from 'vitest';

import { getTextContext } from '../asset.pilot';

describe('asset.pilot', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('includes the current page IP and page number', () => {
    document.body.innerHTML = `
      <div class="ant-table">
        <table>
          <thead><tr><th>实例</th><th>IP</th><th>操作</th></tr></thead>
          <tbody class="ant-table-tbody">
            <tr class="ant-table-row"><td>web-1</td><td>10.0.0.8</td><td><button>编辑</button></td></tr>
          </tbody>
        </table>
        <ul class="ant-pagination">
          <li class="ant-pagination-total-text">共 30 项</li>
          <li class="ant-pagination-item ant-pagination-item-2 ant-pagination-item-active">2</li>
        </ul>
      </div>
    `;
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('10.0.0.8');
    expect(text).toContain('当前第 2 页');
    expect(text).not.toContain('编辑');
    expect(text).not.toContain('page-1-only');
  });
});
