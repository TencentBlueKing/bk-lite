import { afterEach, describe, expect, it } from 'vitest';

import { getTextContext } from '../template.pilot';

describe('template.pilot', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('includes visible template names and checked state', () => {
    document.body.innerHTML = `
      <span class="ant-tree-node-selected">主机</span>
      <span class="groupName_x">CPU</span>
      <button type="button" aria-pressed="true">
        <span class="cardTitleText_x">CPU 高</span>
      </button>
      <button type="button" aria-pressed="false">
        <span class="cardTitleText_x">内存高</span>
      </button>
    `;
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('CPU 高 (已勾选)');
    expect(text).toContain('内存高 (未勾选)');
    expect(text).toContain('不得替用户勾选');
  });
});
