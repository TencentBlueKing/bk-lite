import { afterEach, describe, expect, it } from 'vitest';

import { getTextContext } from '../configure.pilot';

describe('configure.pilot secrets', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('keeps non-secret facts and drops password values', () => {
    window.history.replaceState({}, '', '/monitor/integration/list/detail/configure?plugin_name=Host&name=Host');
    document.body.innerHTML = `
      <form>
        <div class="ant-form-item">
          <label>节点</label>
          <div class="ant-select"><span class="ant-select-selection-item">node-1</span></div>
        </div>
        <div class="ant-form-item">
          <label>Community</label>
          <span class="ant-input-password"><input type="password" value="super-secret-community" /></span>
        </div>
      </form>
    `;
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('node-1');
    expect(text).toContain('plugin_name: Host');
    expect(text).not.toContain('super-secret-community');
  });
});
