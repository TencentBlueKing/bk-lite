import { afterEach, describe, expect, it } from 'vitest';

import {
  buildLogSearchCurrentTime,
  getContext,
  getMessage,
  getTextContext,
  readLogSearchStamp,
} from '../search.pilot';

const setSearchView = (search = '') => {
  window.history.replaceState({}, '', `/log/search${search}`);
};

const segmented = (checked: 'list' | 'overview') => `
  <div class="ant-segmented" role="radiogroup">
    <label class="ant-segmented-item">
      <input class="ant-segmented-item-input" type="radio"${checked === 'list' ? ' checked' : ''} />
      <div class="ant-segmented-item-label">列表</div>
    </label>
    <label class="ant-segmented-item">
      <input class="ant-segmented-item-input" type="radio"${checked === 'overview' ? ' checked' : ''} />
      <div class="ant-segmented-item-label">终端</div>
    </label>
  </div>
`;

const searchShell = (body: string, view: 'list' | 'overview' = 'list') => `
  <div class="search_x">
    <div class="searchCondition_x">
      <div class="ant-select ant-select-multiple">
        <span class="ant-select-selection-item">k8s-prod</span>
        <input class="ant-select-selection-search-input ant-input" value="should-not-use" />
      </div>
      <span class="ant-input-affix-wrapper">
        <input class="ant-input" value="error AND timeout" />
      </span>
    </div>
    ${segmented(view)}
    <div class="timeSelector_x">
      <div class="customSlect_x">
        <div class="ant-select"><span class="ant-select-selection-item">最近15分钟</span></div>
        <div class="ant-picker">
          <div class="ant-picker-input"><input value="" /></div>
          <div class="ant-picker-input"><input value="" /></div>
        </div>
      </div>
      <div class="refreshBox_x">
        <div class="ant-select"><span class="ant-select-selection-item">30秒</span></div>
      </div>
    </div>
    ${body}
  </div>
`;

describe('search.pilot gate', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setSearchView('');
  });

  it('does not produce a page snapshot in terminal mode', () => {
    setSearchView('');
    document.body.innerHTML = searchShell('', 'overview');
    expect(getMessage().title).toBe('');
    expect(getTextContext().sections || []).toEqual([]);
  });

  it('uses list view in title', () => {
    setSearchView('');
    document.body.innerHTML = searchShell('', 'list');
    expect(getMessage().title).toBe('log-search:list');
  });
});

describe('search.pilot fingerprint', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setSearchView('');
  });

  it('changes currentTime when query changes, not when only refresh interval changes', () => {
    document.body.innerHTML = searchShell(`
      <div class="collapse-title"><span>日志总条数：</span><span>12</span></div>
      <div class="tableArea_x">
        <table>
          <thead><tr><th></th><th>timestamp</th><th>message</th></tr></thead>
          <tbody>
            <tr class="ant-table-row"><td></td><td>10:00</td><td>boom</td></tr>
          </tbody>
        </table>
      </div>
    `);
    const first = buildLogSearchCurrentTime(readLogSearchStamp());
    document.querySelector('.refreshBox_x .ant-select-selection-item')!.textContent = '1分钟';
    expect(buildLogSearchCurrentTime(readLogSearchStamp())).toBe(first);
    (document.querySelector('.ant-input-affix-wrapper input.ant-input') as HTMLInputElement).value = 'status:500';
    expect(buildLogSearchCurrentTime(readLogSearchStamp())).not.toBe(first);
  });
});

describe('search.pilot text context', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setSearchView('');
  });

  it('reads DOM query, time, groups, visible main-row messages, and redacts tokens', () => {
    document.body.innerHTML = searchShell(`
      <div class="collapse-title"><span>日志总条数：</span><span>128</span></div>
      <div class="tableArea_x">
        <table>
          <thead><tr><th></th><th>timestamp</th><th>message</th><th>host</th></tr></thead>
          <tbody>
            <tr class="ant-table-row">
              <td></td>
              <td>2026-09-18 10:00:00</td>
              <td>auth failed Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload</td>
              <td>host-a</td>
            </tr>
            <tr class="ant-table-expanded-row">
              <td colspan="4">password=should-not-appear host-a</td>
            </tr>
          </tbody>
        </table>
      </div>
    `);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('正在查看日志搜索');
    expect(text).toContain('error AND timeout');
    expect(text).toContain('最近15分钟');
    expect(text).toContain('k8s-prod');
    expect(text).toContain('128');
    expect(text).toContain('2026-09-18 10:00:00');
    expect(text).toContain('Bearer [已省略]');
    expect(text).not.toContain('eyJhbGciOiJIUzI1NiJ9');
    expect(text).not.toContain('should-not-use');
    expect(text).not.toContain('password=should-not-appear');
    expect(text).not.toContain('host-a');
  });

  it('getContext returns text only without histogram images and does not log query or row text', async () => {
    document.body.innerHTML = searchShell(`
      <div class="collapse-title"><span>日志总条数：</span><span>3</span></div>
      <div class="tableArea_x">
        <table>
          <thead><tr><th></th><th>timestamp</th><th>message</th></tr></thead>
          <tbody>
            <tr class="ant-table-row"><td></td><td>10:00</td><td>boom secret-line</td></tr>
          </tbody>
        </table>
      </div>
    `);
    const logged: unknown[] = [];
    const originalInfo = console.info;
    console.info = (...args: unknown[]) => {
      logged.push(args);
    };
    try {
      const snapshot = await getContext({
        captureEchartsFromDoms: async () => [{ caption: 'should-not', dataUrl: 'data:x' }],
        captureEchartsFromDom: async () => [],
        captionFromOption: () => '',
      });
      expect(snapshot.images || []).toEqual([]);
      expect((snapshot.sections || []).map((section) => section.content).join('\n')).toContain('boom');
      const serialized = JSON.stringify(logged);
      expect(serialized).not.toContain('error AND timeout');
      expect(serialized).not.toContain('boom secret-line');
    } finally {
      console.info = originalInfo;
    }
  });

  it('reads custom time range from picker inputs', () => {
    document.body.innerHTML = searchShell('');
    const inputs = document.querySelectorAll<HTMLInputElement>('.ant-picker-input input');
    inputs[0].value = '2026-09-18 00:00:00';
    inputs[1].value = '2026-09-18 01:00:00';
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('2026-09-18 00:00:00 ~ 2026-09-18 01:00:00');
  });
});
