import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLatestRequestGuard } from '../src/context/latestRequestGuard.ts';

interface SearchViewState {
  tableData: Array<{ id: string }>;
  chartData: Array<{ id: string }>;
  tableLoading: boolean;
  chartLoading: boolean;
}

const here = dirname(fileURLToPath(import.meta.url));
const pagePath = resolve(here, '../src/app/log/(pages)/search/page.tsx');
const apiPath = resolve(here, '../src/app/log/api/search.ts');
const guardPath = resolve(here, '../src/context/latestRequestGuard.ts');

function createSearchSession() {
  const guard = createLatestRequestGuard();
  let aborted: number[] = [];
  let activeRequestId = 0;
  let state: SearchViewState = {
    tableData: [],
    chartData: [],
    tableLoading: false,
    chartLoading: false,
  };

  const start = () => {
    if (activeRequestId) {
      aborted.push(activeRequestId);
    }
    const requestId = guard.begin();
    activeRequestId = requestId;
    state = {
      ...state,
      tableData: [],
      chartData: [],
      tableLoading: true,
      chartLoading: true,
    };
    return requestId;
  };

  const commitTable = (requestId: number, rows: Array<{ id: string }>) => {
    guard.commitIfCurrent(requestId, () => {
      state = { ...state, tableData: rows };
    });
  };

  const commitChart = (requestId: number, rows: Array<{ id: string }>) => {
    guard.commitIfCurrent(requestId, () => {
      state = { ...state, chartData: rows };
    });
  };

  const settleTable = (requestId: number) => {
    guard.commitIfCurrent(requestId, () => {
      state = { ...state, tableLoading: false };
    });
  };

  const settleChart = (requestId: number) => {
    guard.commitIfCurrent(requestId, () => {
      state = { ...state, chartLoading: false };
    });
  };

  return {
    getState: () => state,
    wasAborted: (requestId: number) => aborted.includes(requestId),
    start,
    commitTable,
    commitChart,
    settleTable,
    settleChart,
  };
}

function assertPageUsesGeneration(source: string) {
  assert.match(
    source,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'page 必须复用 @/context/latestRequestGuard，不得复制新 guard',
  );
  assert.match(source, /createLatestRequestGuard/, 'page 必须创建 latest request guard');
  assert.match(source, /requestGuard\.begin\(\)/, 'getLogData 必须为每次查询分配代次');
  assert.match(
    source,
    /requestGuard\.commitIfCurrent\([\s\S]*?setTableData\(/,
    '列表只能由当前代次提交',
  );
  assert.match(
    source,
    /requestGuard\.commitIfCurrent\([\s\S]*?setChartData\(/,
    '图表只能由当前代次提交',
  );
  assert.match(
    source,
    /requestGuard\.commitIfCurrent\([\s\S]*?setTableLoading\(false\)/,
    '旧批次 finally 不得无条件清掉新批次 table loading',
  );
  assert.match(
    source,
    /requestGuard\.commitIfCurrent\([\s\S]*?setChartLoading\(false\)/,
    '旧批次 finally 不得无条件清掉新批次 chart loading',
  );
  assert.match(source, /AbortController/, '新查询必须 abort 旧请求');
  assert.match(source, /\.abort\(\)/, '新查询必须 abort 旧请求');
  const canceledGuards = source.match(
    /if \(signal\.aborted \|\| isCanceledRequest\(error\)\)/g,
  );
  assert.equal(
    canceledGuards?.length,
    2,
    'getChartData 与 getTableData 必须在 catch 中用 signal.aborted 识别取消，避免拦截器把 CanceledError 包成 HandledRequestError 后误抛',
  );
  assert.match(
    source,
    /getHits\([\s\S]*?\{\s*signal/,
    'getHits 必须传入 AbortSignal',
  );
  assert.match(
    source,
    /getLogs\([\s\S]*?\{\s*signal/,
    'getLogs 必须传入 AbortSignal',
  );
  assert.match(source, /min=\{1\}/, '条数下限必须仍为 1');
  assert.match(source, /max=\{1000\}/, '条数上限必须仍为 1000');
  assert.match(
    source,
    /!extra\?\.logGroups\?\.length && !groups\.length/,
    '分组为空时的检索拦截必须保留',
  );
  assert.doesNotMatch(
    source,
    /function createLatestRequestGuard|const createLatestRequestGuard\s*=/,
    '不得在 page 内复制一套序号 guard',
  );
  assert.doesNotMatch(
    source,
    /setTableData\(listData\);\s*\}\s*finally \{\s*setTableLoading\(false\)/,
    'getTableData 不得在 await 后无条件 setTableData 并由 finally 清 loading',
  );
  assert.doesNotMatch(
    source,
    /setChartData\(chartData\);\s*\}\s*finally \{\s*setChartLoading\(false\)/,
    'getChartData 不得在 await 后无条件 setChartData 并由 finally 清 loading',
  );
  assert.doesNotMatch(
    source,
    /finally \{\s*setTableLoading\(false\);/,
    'getTableData 不得在 finally 无条件清 loading',
  );
  assert.doesNotMatch(
    source,
    /finally \{\s*setChartLoading\(false\);/,
    'getChartData 不得在 finally 无条件清 loading',
  );
}

function assertApiAcceptsHitsConfig(source: string) {
  assert.match(
    source,
    /const getHits = async \(data: SearchParams, config\?: AxiosRequestConfig\)/,
    'getHits 必须接受 AxiosRequestConfig',
  );
  assert.match(
    source,
    /post\(`\/log\/search\/hits\/`, data, config\)/,
    'getHits 必须把 config 传给 hits 请求',
  );
  assert.match(source, /post\(`\/log\/search\/search\/`, data, config\)/, '不得改 search 路径');
  assert.match(source, /post\(`\/log\/search\/hits\/`, data/, '不得改 hits 路径');
}

function main() {
  const guardSource = readFileSync(guardPath, 'utf8');
  assert.match(guardSource, /export const createLatestRequestGuard/, '必须复用已有 latestRequestGuard');

  const race = createSearchSession();
  const requestA = race.start();
  const requestB = race.start();
  assert.ok(race.wasAborted(requestA), '新查询必须 abort 旧请求');
  race.commitTable(requestB, [{ id: 'table-B' }]);
  race.commitChart(requestB, [{ id: 'chart-B' }]);
  race.settleTable(requestB);
  race.settleChart(requestB);
  race.commitTable(requestA, [{ id: 'table-A' }]);
  race.commitChart(requestA, [{ id: 'chart-A' }]);
  race.settleTable(requestA);
  race.settleChart(requestA);
  assert.deepEqual(race.getState().tableData, [{ id: 'table-B' }], 'A 后到不得覆盖 B 的列表');
  assert.deepEqual(race.getState().chartData, [{ id: 'chart-B' }], 'A 后到不得覆盖 B 的图表');
  assert.equal(race.getState().tableLoading, false);
  assert.equal(race.getState().chartLoading, false);

  const staleFinally = createSearchSession();
  const oldInflight = staleFinally.start();
  staleFinally.start();
  staleFinally.commitTable(oldInflight, [{ id: 'table-old' }]);
  staleFinally.commitChart(oldInflight, [{ id: 'chart-old' }]);
  staleFinally.settleTable(oldInflight);
  staleFinally.settleChart(oldInflight);
  assert.deepEqual(staleFinally.getState().tableData, [], '旧成功不得在最新请求仍在途时写回列表');
  assert.deepEqual(staleFinally.getState().chartData, [], '旧成功不得在最新请求仍在途时写回图表');
  assert.equal(staleFinally.getState().tableLoading, true, '旧 finally 不得清掉新批次 table loading');
  assert.equal(staleFinally.getState().chartLoading, true, '旧 finally 不得清掉新批次 chart loading');

  const mixed = createSearchSession();
  const mixedA = mixed.start();
  const mixedB = mixed.start();
  mixed.commitChart(mixedA, [{ id: 'chart-A' }]);
  mixed.commitTable(mixedB, [{ id: 'table-B' }]);
  mixed.settleChart(mixedA);
  mixed.commitChart(mixedB, [{ id: 'chart-B' }]);
  mixed.settleTable(mixedB);
  mixed.settleChart(mixedB);
  assert.deepEqual(mixed.getState().tableData, [{ id: 'table-B' }], '图表与列表必须同属最新世代');
  assert.deepEqual(mixed.getState().chartData, [{ id: 'chart-B' }], '旧图表不得与新列表混批');
  assert.equal(mixed.getState().tableLoading, false);
  assert.equal(mixed.getState().chartLoading, false);

  const pageSource = readFileSync(pagePath, 'utf8');
  const apiSource = readFileSync(apiPath, 'utf8');
  assertPageUsesGeneration(pageSource);
  assertApiAcceptsHitsConfig(apiSource);

  console.log('log search query generation test passed');
}

main();
