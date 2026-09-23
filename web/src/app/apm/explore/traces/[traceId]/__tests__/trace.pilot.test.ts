import { afterEach, describe, expect, it } from 'vitest';

import { getMessage, getTextContext, readErrorSpanLines } from '../trace.pilot';

const setTraceView = (path = '/apm/explore/traces/abc123') => {
  window.history.replaceState({}, '', path);
};

const viewSegmented = (checked: 'waterfall' | 'flame' | 'list') => {
  const values = ['waterfall', 'flame', 'list'] as const;
  return `
    <div class="ant-segmented" role="radiogroup" aria-label="Trace 视图模式">
      ${values.map((value) => `
        <label class="ant-segmented-item">
          <input class="ant-segmented-item-input" type="radio"${value === checked ? ' checked' : ''} />
        </label>
      `).join('')}
    </div>
  `;
};

const kpi = `
  <span class="sr-only">Trace ID</span>
  <span class="font-mono">abc123</span>
  <div>
    <span class="text-xs font-medium">Span 数</span>
    <div class="text-xl font-bold tabular-nums">12</div>
  </div>
  <div>
    <span class="text-xs font-medium">错误 Span</span>
    <div class="text-xl font-bold tabular-nums">12</div>
  </div>
  <div>
    <span class="text-xs font-medium">服务数</span>
    <div class="text-xl font-bold tabular-nums">3</div>
  </div>
  <div>
    <span class="text-xs font-medium">总耗时</span>
    <div class="text-xl font-bold tabular-nums">1.2s</div>
  </div>
`;

const breakdown = `
  <div>
    <strong>服务耗时分解</strong>
    <div class="flex items-center gap-2">
      <span class="font-mono">checkout</span>
      <span class="tabular-nums">42.0%</span>
      <span class="tabular-nums">320ms</span>
    </div>
    <div class="flex items-center gap-2">
      <span class="font-mono">payments</span>
      <span class="tabular-nums">31.0%</span>
      <span class="tabular-nums">240ms</span>
    </div>
  </div>
`;

describe('trace.pilot gate', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setTraceView();
  });

  it('does not produce a snapshot on the trace list', () => {
    setTraceView('/apm/explore/traces');
    document.body.innerHTML = `${kpi}${viewSegmented('waterfall')}`;
    expect(getMessage().title).toBe('');
    expect(getTextContext().sections || []).toEqual([]);
  });

  it('uses trace id in title', () => {
    setTraceView('/apm/explore/traces/abc123');
    document.body.innerHTML = `${kpi}${viewSegmented('waterfall')}`;
    expect(getMessage().title).toBe('apm-trace:abc123');
  });
});

describe('trace.pilot collection', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setTraceView('/apm/explore/traces/abc123');
  });

  it('reads identity and service breakdown', () => {
    document.body.innerHTML = `${kpi}${viewSegmented('waterfall')}${breakdown}`;
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('Trace ID: abc123');
    expect(text).toContain('错误 Span: 12');
    expect(text).toContain('总耗时: 1.2s');
    expect(text).toContain('checkout 42.0% 320ms');
    expect(text).toContain('payments 31.0% 240ms');
    expect((getTextContext().sections || []).map((section) => `${section.id}:${section.priority}`)).toEqual([
      'apm-trace-identity:10',
      'apm-trace-breakdown:9',
      'apm-trace-errors:8',
    ]);
  });

  it('reads Typography.Text headings and selected span from sibling sections', () => {
    document.body.innerHTML = `
      ${kpi}${viewSegmented('waterfall')}
      <div class="sticky">
        <section>
          <div class="mb-3 flex items-center justify-between">
            <span class="ant-typography"><strong>服务耗时分解</strong></span>
          </div>
          <div class="flex flex-col gap-2">
            <div class="flex items-center gap-2">
              <span class="w-24 shrink-0 truncate font-mono text-xs">checkout</span>
              <span class="tabular-nums">42.0%</span>
              <span class="tabular-nums">320ms</span>
            </div>
          </div>
        </section>
        <section>
          <span class="ant-typography mb-3 block"><strong>Span 详情</strong></span>
          <span class="font-mono">GET /cart</span>
          <table class="ant-descriptions">
            <tr class="ant-descriptions-item">
              <th class="ant-descriptions-item-label">总耗时</th>
              <td class="ant-descriptions-item-content">40ms</td>
            </tr>
          </table>
          <table><tbody><tr><td>http.route</td><td>/cart</td></tr></tbody></table>
        </section>
      </div>
    `;
    const first = getMessage().currentTime;
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('checkout 42.0% 320ms');
    expect(text).toContain('名称: GET /cart');
    expect(text).toContain('总耗时: 40ms');
    expect(text).toContain('http.route: /cart');
    const selectedName = Array.from(document.querySelectorAll('section .font-mono')).find(
      (node) => node.textContent === 'GET /cart',
    );
    selectedName!.textContent = 'POST /pay';
    document.querySelector('.ant-descriptions-item-content')!.textContent = '280ms';
    expect(getMessage().currentTime).not.toBe(first);
    expect((getTextContext().sections || []).map((section) => section.content).join('\n')).toContain('名称: POST /pay');
  });

  it('notes truncated traces in identity', () => {
    document.body.innerHTML = `
      ${kpi}${viewSegmented('waterfall')}
      <div class="ant-alert ant-alert-warning"><span class="ant-alert-message">Trace 响应已达到安全上限，当前展示部分 Span 或属性。</span></div>
    `;
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('展示部分 Span');
  });

  it('recognizes waterfall errors by error tag, not by duration color', () => {
    document.body.innerHTML = `
      ${kpi}${viewSegmented('waterfall')}
      <button type="button">
        <span class="ant-tag ant-tag-error">CLIENT</span>
        <span class="font-mono">POST /pay</span>
        <span class="text-[var(--color-text-3)]">checkout</span>
        <div class="w-24 text-right text-xs tabular-nums text-[var(--color-text-2)]">12ms</div>
      </button>
      <button type="button">
        <span class="ant-tag">SERVER</span>
        <span class="font-mono">GET /ok</span>
        <span class="text-[var(--color-text-3)]">api</span>
        <div class="w-24 text-right text-xs tabular-nums text-[var(--color-fail)]">200ms</div>
      </button>
    `;
    expect(readErrorSpanLines('waterfall')).toEqual(['checkout · POST /pay · 12ms']);
  });

  it('recognizes list errors by warning mark and respects span query', () => {
    document.body.innerHTML = `
      ${kpi}${viewSegmented('list')}
      <input aria-label="搜索跨度名或服务" value="checkout" />
      <button type="button">
        <span class="font-mono">POST /pay</span>
        <span class="text-[var(--color-text-3)]">checkout</span>
        <span>12ms ⚠</span>
      </button>
      <button type="button">
        <span class="font-mono">slow ok</span>
        <span class="text-[var(--color-text-3)]">api</span>
        <span class="text-[var(--color-fail)]">200ms</span>
      </button>
    `;
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('列表已过滤');
    expect(text).toContain('checkout · POST /pay · 12ms ⚠');
    expect(text).not.toContain('slow ok');
  });

  it('recognizes flame errors by color-fail background', () => {
    document.body.innerHTML = `
      ${kpi}${viewSegmented('flame')}
      <button type="button" style="left: 0%; background: var(--color-fail)" aria-label="checkout · POST /pay"></button>
      <button type="button" style="background: color-mix(in srgb, var(--color-primary) 40%, var(--color-fail))" aria-label="inventory · reserve"></button>
      <button type="button" style="background: var(--theme-color-chart-primary)" aria-label="api · GET /ok"></button>
    `;
    expect(readErrorSpanLines('flame')).toEqual(['checkout · POST /pay']);
  });

  it('caps error spans at 8 and attributes at 20, and redacts selected span values', () => {
    const errorButtons = Array.from({ length: 10 }, (_, index) => `
      <button type="button">
        <span class="ant-tag ant-tag-error">CLIENT</span>
        <span class="font-mono">err-${index + 1}</span>
        <span class="text-[var(--color-text-3)]">svc</span>
        <span class="tabular-nums">${index}ms</span>
      </button>
    `).join('');
    const attrRows = Array.from({ length: 22 }, (_, index) => (
      index === 0
        ? '<tr><td>authorization</td><td>Bearer abc.def</td></tr>'
        : `<tr><td>k${index}</td><td>v${index}</td></tr>`
    )).join('');
    document.body.innerHTML = `
      ${kpi}${viewSegmented('waterfall')}${errorButtons}
      <div>
        <strong>Span 详情</strong>
        <span class="font-mono">POST /pay</span>
        <table><tbody>${attrRows}</tbody></table>
      </div>
    `;
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('err-1');
    expect(text).toContain('err-8');
    expect(text).not.toContain('err-9');
    expect(text).toContain('共 12 个，以下可见 8 条');
    expect(text).toContain('属性共 22 项，已附 20 项');
    expect(text).toContain('authorization: Bearer [已省略]');
    expect(text).not.toContain('Bearer abc.def');
    expect(text).toContain('k19: v19');
    expect(text).not.toContain('k21: v21');
  });
});
