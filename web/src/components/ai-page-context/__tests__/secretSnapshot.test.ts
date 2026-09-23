import { describe, expect, it } from 'vitest';

import { readVisibleFormFacts } from '../secretSnapshot';

describe('secretSnapshot', () => {
  it('skips password controls even when the label is not recognized', () => {
    document.body.innerHTML = `
      <div class="ant-form-item">
        <label>节点</label>
        <input value="node-1" />
      </div>
      <div class="ant-form-item">
        <label>Token</label>
        <input value="should-skip-by-label" />
      </div>
      <div class="ant-form-item">
        <label>其它</label>
        <input type="password" value="hidden-pass" />
      </div>
    `;
    const facts = readVisibleFormFacts().join('\n');
    expect(facts).toContain('node-1');
    expect(facts).not.toContain('should-skip-by-label');
    expect(facts).not.toContain('hidden-pass');
  });
});
