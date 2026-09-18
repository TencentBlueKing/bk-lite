import { afterEach, describe, expect, it, vi } from 'vitest';

import type { PageContextToolkit } from '@/components/ai-page-context/types';

import {
  getContext,
  getMessage,
  getTextContext,
} from '../service.pilot';

const setServiceView = (path = '/apm/services/svc-1', search = '?environment=prod') => {
  window.history.replaceState({}, '', `${path}${search}`);
};

const toolkit: PageContextToolkit = {
  captureEchartsFromDoms: vi.fn(async (doms) =>
    doms.map((dom) => ({
      caption: `图表；横轴: 10:00~11:00`,
      dataUrl: `data:image/jpeg;base64,${dom.id || 'x'}`,
    })),
  ),
  captureEchartsFromDom: vi.fn(async () => []),
  captionFromOption: vi.fn(() => ''),
};

const joined = () => (getTextContext().sections || []).map((section) => section.content).join('\n');

const serviceShell = (tab: string, extra = '') => `
  <h2 class="ant-typography">checkout</h2>
  <div class="ant-select" aria-label="选择环境"><span class="ant-select-selection-item">prod</span></div>
  <div class="ant-segmented">
    <div class="ant-segmented-item ant-segmented-item-selected">
      <div class="ant-segmented-item-label">1h</div>
    </div>
  </div>
  <div class="grid">
    <div>
      <span class="text-xs font-medium">吞吐</span>
      <div><span class="text-2xl font-bold tabular-nums">12.3</span><span>req/s</span></div>
    </div>
    <div>
      <span class="text-xs font-medium">错误率</span>
      <div><span class="text-2xl font-bold tabular-nums">2.1%</span></div>
    </div>
    <div>
      <span class="text-xs font-medium">P99</span>
      <div><span class="text-2xl font-bold tabular-nums">320</span><span>毫秒</span></div>
    </div>
    <div>
      <span class="text-xs font-medium">P95</span>
      <div><span class="text-2xl font-bold tabular-nums">180</span><span>毫秒</span></div>
    </div>
  </div>
  <div class="ant-tabs-tab ant-tabs-tab-active" data-node-key="${tab}">${tab}</div>
  <div class="ant-tabs">${extra}</div>
`;

const overviewBody = `
  <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
    <section>
      <span class="ant-typography"><strong>吞吐量</strong></span>
      <div id="overview-chart" _echarts_instance_="red"></div>
    </section>
    <section>
      <span class="ant-typography"><strong>Top 端点</strong></span>
      <div class="ant-list">
        <div class="ant-list-item">
          <a>POST /pay</a>
          <span class="tabular-nums">12 req/s · P99 380ms</span>
        </div>
        <div class="ant-list-item">
          <a>GET /cart</a>
          <span class="tabular-nums">4 req/s · P99 90ms</span>
        </div>
      </div>
    </section>
    <section>
      <span class="ant-typography"><strong>依赖关系</strong></span>
      <span class="ant-typography">上游 · 调用方 1</span>
      <span class="ant-tag">gateway · 40/窗 · Pavg 12ms · 错误 1</span>
      <span class="ant-typography">近窗内无向下调用</span>
    </section>
  </div>
`;

describe('service.pilot gate', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setServiceView();
  });

  it('does not produce a snapshot on reserved service routes', () => {
    setServiceView('/apm/services/slo');
    document.body.innerHTML = serviceShell('overview');
    expect(getMessage().title).toBe('');
    expect(getTextContext().sections || []).toEqual([]);
  });

  it('uses serviceId in title', () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('overview');
    expect(getMessage().title).toBe('apm-service:svc-1');
  });
});

describe('service.pilot text and charts', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setServiceView();
    vi.clearAllMocks();
  });

  it('keeps shell KPI on a non-overview tab and captures the errors-tab trend chart only', async () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('errors', `
      <div class="ant-tabs-tabpane" aria-hidden="true">
        <section>
          <span class="ant-typography"><strong>Top 端点</strong></span>
          <div class="ant-list-item"><a>POST /pay</a><span class="tabular-nums">12 req/s · P99 380ms</span></div>
        </section>
        <strong>吞吐量</strong>
        <div id="overview-chart" _echarts_instance_="red"></div>
      </div>
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <span class="text-xs font-medium">入口请求</span>
        <span class="text-2xl font-bold tabular-nums">10</span>
        <span class="text-sm font-semibold">错误率趋势</span>
        <div id="error-chart" role="img" aria-label="错误率趋势" _echarts_instance_="err"></div>
      </div>
    `);
    const text = joined();
    expect(text).toContain('正在查看 APM 服务详情');
    expect(text).toContain('checkout');
    expect(text).toContain('svc-1');
    expect(text).toContain('prod');
    expect(text).toContain('1h');
    expect(text).toContain('吞吐: 12.3 req/s');
    expect(text).toContain('错误率: 2.1%');
    expect(text).toContain('入口请求: 10');
    expect(text).not.toContain('POST /pay');
    const full = await getContext(toolkit);
    expect(full.images).toHaveLength(1);
    expect(full.images?.[0].caption?.startsWith('错误率趋势')).toBe(true);
    expect(full.images?.[0].dataUrl).toContain('error-chart');
    expect(toolkit.captureEchartsFromDoms).toHaveBeenCalledTimes(1);
  });

  it('ignores error-tab KPI cards that stay in hidden tab panes', () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = `${serviceShell('overview')}
      <div class="ant-tabs">
        <div class="ant-tabs-tabpane" aria-hidden="true">
          <span class="text-xs font-medium">入口请求</span>
          <div><span class="text-2xl font-bold tabular-nums">999</span></div>
          <span class="text-xs font-medium">失败次数</span>
          <div><span class="text-2xl font-bold tabular-nums">88</span></div>
        </div>
      </div>
    `;
    const text = joined();
    expect(text).toContain('吞吐: 12.3 req/s');
    expect(text).not.toContain('入口请求');
    expect(text).not.toContain('999');
    expect(text).not.toContain('失败次数');
  });

  it('reads overview endpoints and dependencies from sibling sections, not hidden panes', () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('overview', `
      ${overviewBody}
      <div class="ant-tabs-tabpane" aria-hidden="true">
        <section>
          <span class="ant-typography"><strong>近窗调用链样本</strong></span>
          <table><tbody><tr class="ant-table-row"><td>hidden-trace</td><td>错误</td></tr></tbody></table>
        </section>
      </div>
    `);
    const text = joined();
    expect(text).toContain('POST /pay · 12 req/s · P99 380ms');
    expect(text).toContain('GET /cart');
    expect(text).toContain('上游 · 调用方 1');
    expect(text).toContain('gateway · 40/窗 · Pavg 12ms · 错误 1');
    expect(text).toContain('近窗内无向下调用');
    expect(text).not.toContain('hidden-trace');
  });

  it('accepts English overview headings', () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('overview', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <section>
          <span class="ant-typography"><strong>Top endpoints</strong></span>
          <div class="ant-list-item"><a>POST /pay</a><span class="tabular-nums">1 req/s · P99 10ms</span></div>
        </section>
        <section>
          <span class="ant-typography"><strong>Dependencies</strong></span>
          <span class="ant-typography">No upstream calls in the recent window</span>
        </section>
      </div>
    `);
    const text = joined();
    expect(text).toContain('POST /pay');
    expect(text).toContain('No upstream calls in the recent window');
  });

  it('reads the traces table from the active pane and skips overview charts', async () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('traces', `
      <div class="ant-tabs-tabpane" aria-hidden="true">${overviewBody.replace('ant-tabs-tabpane-active', '')}</div>
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <section>
          <span class="ant-typography"><strong>近窗调用链样本</strong></span>
          <table>
            <thead><tr><th>Trace ID</th><th>入口服务</th><th>资源</th><th>总耗时</th><th>跨度数</th><th>状态</th></tr></thead>
            <tbody>
              <tr class="ant-table-row">
                <td><a>trace-aaa</a></td>
                <td>checkout</td>
                <td>GET /cart</td>
                <td>80ms</td>
                <td>4</td>
                <td><span class="ant-tag">错误</span></td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    `);
    const text = joined();
    expect(text).toContain('trace-aaa');
    expect(text).toContain('GET /cart');
    expect(text).toContain('80ms');
    expect(text).toContain('错误');
    expect(text).not.toContain('POST /pay');
    const full = await getContext(toolkit);
    expect(full.images || []).toEqual([]);
  });

  it('redacts error messages, notes endpoint filters, and keeps only visible sample rows', () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('errors', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <div>
          <span class="text-xs font-medium">入口请求</span>
          <span class="text-2xl font-bold tabular-nums">10</span>
        </div>
        <div>
          <span class="text-xs font-medium">失败次数</span>
          <span class="text-2xl font-bold tabular-nums">4</span>
        </div>
        <section>
          <h3 class="ant-typography">错误原因</h3>
          <table>
            <thead><tr><th>类型</th><th>次数</th></tr></thead>
            <tbody>
              <tr class="ant-table-row">
                <td><span>Timeout</span> <span>password=hunter2 long stack</span></td>
                <td>2</td>
              </tr>
            </tbody>
          </table>
        </section>
        <section>
          <h3 class="ant-typography">失败端点</h3>
          <button type="button"><span class="font-mono">POST /checkout</span><span>失败 3</span></button>
        </section>
        <section>
          <h3 class="ant-typography">最近 1 条</h3>
          <button type="button">清除端点筛选</button>
          <table>
            <thead><tr><th>端点</th><th>操作</th></tr></thead>
            <tbody>
              <tr class="ant-table-row"><td>POST /checkout</td><td>详情</td></tr>
              <tr class="ant-table-row" hidden><td>GET /products</td><td>详情</td></tr>
            </tbody>
          </table>
        </section>
      </div>
    `);
    const text = joined();
    expect(text).toContain('入口请求: 10');
    expect(text).toContain('失败次数: 4');
    expect(text).toContain('Timeout');
    expect(text).toContain('key=[已省略]');
    expect(text).not.toContain('hunter2');
    expect(text).toContain('POST /checkout');
    expect(text).toContain('已按端点过滤');
    expect(text).not.toContain('GET /products');
  });

  it('caps deployment rows and keeps runtime / SLO empty copy', () => {
    setServiceView('/apm/services/svc-1');
    const rows = Array.from({ length: 16 }, (_, index) => (
      `<tr class="ant-table-row"><td>v1.${index}</td><td>prod</td><td>成功</td><td>推断</td></tr>`
    )).join('');
    document.body.innerHTML = serviceShell('deployments', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <table>
          <thead><tr><th>版本</th><th>环境</th><th>状态</th><th>来源</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `);
    const deployText = joined();
    expect(deployText).toContain('v1.0');
    expect(deployText).toContain('v1.14');
    expect(deployText).not.toContain('v1.15');

    document.body.innerHTML = serviceShell('runtime', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <span class="ant-typography">该服务尚未接入运行时指标采集（JVM / Go Runtime 等）</span>
      </div>
    `);
    expect(joined()).toContain('尚未接入运行时');

    document.body.innerHTML = serviceShell('slo', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <div class="ant-empty-description">该服务尚未配置 SLO</div>
      </div>
    `);
    expect(joined()).toContain('该服务尚未配置 SLO');
  });

  it('keeps only the shell for unknown tab keys', () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('unknown', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <div class="ant-list-item"><a>POST /secret</a></div>
      </div>
    `);
    const text = joined();
    expect(text).toContain('当前 Tab: unknown');
    expect(text).toContain('吞吐: 12.3 req/s');
    expect(text).not.toContain('POST /secret');
  });

  it('changes currentTime when the tab or visible list changes', () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('overview', overviewBody);
    const overviewTime = getMessage().currentTime;
    document.body.innerHTML = serviceShell('traces', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <section>
          <span class="ant-typography"><strong>近窗调用链样本</strong></span>
          <table><tbody><tr class="ant-table-row"><td>trace-aaa</td><td>错误</td></tr></tbody></table>
        </section>
      </div>
    `);
    const tracesTime = getMessage().currentTime;
    expect(tracesTime).not.toBe(overviewTime);
    document.querySelector('.ant-table-row td')!.textContent = 'trace-bbb';
    expect(getMessage().currentTime).not.toBe(tracesTime);
  });

  it('changes currentTime when error-tab endpoint filter changes even if types already fill the old 400-char prefix', () => {
    setServiceView('/apm/services/svc-1');
    const longType = 'E'.repeat(120);
    const typeRows = Array.from({ length: 4 }, (_, index) => (
      `<tr class="ant-table-row"><td>${longType}-${index} timeout connecting to host</td><td>${index + 1}</td></tr>`
    )).join('');
    document.body.innerHTML = serviceShell('errors', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <div>
          <span class="text-xs font-medium">入口请求</span>
          <span class="text-2xl font-bold tabular-nums">10</span>
        </div>
        <section>
          <h3 class="ant-typography">错误原因</h3>
          <table>
            <thead><tr><th>类型</th><th>次数</th></tr></thead>
            <tbody>${typeRows}</tbody>
          </table>
        </section>
        <section>
          <h3 class="ant-typography">最近 2 条</h3>
          <table>
            <thead><tr><th>端点</th></tr></thead>
            <tbody>
              <tr class="ant-table-row"><td>GET /products</td></tr>
              <tr class="ant-table-row"><td>POST /checkout</td></tr>
            </tbody>
          </table>
        </section>
      </div>
    `);
    const beforeFilter = getMessage().currentTime;
    expect((beforeFilter || '').length).toBeGreaterThan(400);
    document.querySelector('h3.ant-typography:last-of-type')!.insertAdjacentHTML(
      'afterend',
      '<button type="button">清除端点筛选</button>',
    );
    const productRow = Array.from(document.querySelectorAll('.ant-table-row')).find((row) =>
      (row.textContent || '').includes('GET /products'),
    );
    productRow?.setAttribute('hidden', '');
    expect(getMessage().currentTime).not.toBe(beforeFilter);
    const text = joined();
    expect(text).toContain('已按端点过滤');
    expect(text).toContain('POST /checkout');
    expect(text).not.toContain('GET /products');
  });

  it('keeps traces headingRoot inside the active pane and reads Result copy', () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('traces', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <section>
          <span class="ant-typography"><strong>近窗调用链样本</strong></span>
          <div class="ant-result">
            <div class="ant-result-title">APM 数据加载失败</div>
            <div class="ant-result-subtitle">请检查筛选条件或网络状态后重试。</div>
            <button type="button">重新加载</button>
          </div>
        </section>
      </div>
      <div class="ant-tabs-tabpane" aria-hidden="true">
        <table><tbody><tr class="ant-table-row"><td>hidden-trace</td></tr></tbody></table>
      </div>
    `);
    const text = joined();
    expect(text).toContain('APM 数据加载失败');
    expect(text).toContain('请检查筛选条件或网络状态后重试。');
    expect(text).not.toContain('hidden-trace');
  });

  it('falls back to visible overview loading copy when Top 端点 is absent', () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('overview', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <div aria-busy="true" aria-label="加载 APM 数据"></div>
      </div>
    `);
    const text = joined();
    expect(text).toContain('正在查看 APM 服务详情');
    expect(text).toContain('吞吐: 12.3 req/s');
    expect(text).toContain('加载 APM 数据');
  });

  it('reads error-tab CatalogState empty copy when the pane has no KPI or table', () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('errors', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <div class="ant-empty-description">本窗无入口请求</div>
      </div>
    `);
    expect(joined()).toContain('本窗无入口请求');
  });

  it('captures only echarts inside the active overview pane', async () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('overview', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <strong>吞吐量</strong>
        <div id="overview-chart" _echarts_instance_="red"></div>
      </div>
      <div class="ant-tabs-tabpane" aria-hidden="true" style="display:none">
        <strong>错误率</strong>
        <div id="hidden-chart" _echarts_instance_="hidden"></div>
      </div>
    `);
    const full = await getContext(toolkit);
    expect(full.images).toHaveLength(1);
    expect(full.images?.[0].caption?.startsWith('吞吐量')).toBe(true);
    expect(full.images?.[0].dataUrl).toContain('overview-chart');
  });

  it('captures at most three RED charts in the overview pane', async () => {
    setServiceView('/apm/services/svc-1');
    document.body.innerHTML = serviceShell('overview', `
      <div class="ant-tabs-tabpane ant-tabs-tabpane-active">
        <span class="ant-typography">吞吐量</span><div id="c1" _echarts_instance_="1"></div>
        <span class="ant-typography">错误率</span><div id="c2" _echarts_instance_="2"></div>
        <span class="ant-typography">延迟趋势</span><div id="c3" _echarts_instance_="3"></div>
        <span class="ant-typography">额外</span><div id="c4" _echarts_instance_="4"></div>
      </div>
    `);
    const full = await getContext(toolkit);
    expect(full.images).toHaveLength(3);
    expect(full.images?.map((image) => image.caption?.split('；')[0])).toEqual([
      '吞吐量',
      '错误率',
      '延迟趋势',
    ]);
  });
});
