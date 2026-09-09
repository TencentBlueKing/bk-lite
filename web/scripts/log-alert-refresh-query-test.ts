import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

interface AlertRefreshFilters {
  level: string[];
  state: string[];
}

interface AlertRefreshQueryState {
  activeTab: string;
  filters: AlertRefreshFilters;
  myAlert: boolean;
}

interface AlertRefreshExtra {
  tab?: string;
  filtersConfig?: AlertRefreshFilters;
  myAlert?: boolean;
}

interface AlertRefreshQuerySnapshot {
  current: AlertRefreshQueryState;
}

interface LoadedModule {
  createAlertRefreshQuerySnapshot?: (
    initial: AlertRefreshQueryState
  ) => AlertRefreshQuerySnapshot;
  updateAlertRefreshQuerySnapshot?: (
    snapshot: AlertRefreshQuerySnapshot,
    next: AlertRefreshQueryState
  ) => void;
  resolveAlertRefreshQuery?: (
    snapshot: AlertRefreshQuerySnapshot,
    extra?: AlertRefreshExtra
  ) => AlertRefreshQueryState;
}

const here = dirname(fileURLToPath(import.meta.url));
const pagePath = resolve(
  here,
  '../src/app/log/(pages)/event/alert/page.tsx'
);

function toQueryFields(state: AlertRefreshQueryState) {
  return {
    status: state.activeTab === 'activeAlarms' ? 'new' : 'closed',
    levels: state.filters.level.join(',')
  };
}

async function loadModule(): Promise<LoadedModule> {
  try {
    return (await import(
      '../src/app/log/(pages)/event/alert/alertRefreshQuery.ts'
    )) as LoadedModule;
  } catch {
    return {};
  }
}

async function main() {
  const loaded = await loadModule();
  assert.equal(
    typeof loaded.createAlertRefreshQuerySnapshot,
    'function',
    '应抽出 createAlertRefreshQuerySnapshot'
  );
  assert.equal(
    typeof loaded.updateAlertRefreshQuerySnapshot,
    'function',
    '应抽出 updateAlertRefreshQuerySnapshot'
  );
  assert.equal(
    typeof loaded.resolveAlertRefreshQuery,
    'function',
    '应抽出 resolveAlertRefreshQuery'
  );

  const snapshot = loaded.createAlertRefreshQuerySnapshot!({
    activeTab: 'activeAlarms',
    filters: { level: [], state: [] },
    myAlert: false
  });

  // 模拟 setInterval：创建定时器时不带 extra，后续 tick 必须读最新快照
  const timerTick = () => loaded.resolveAlertRefreshQuery!(snapshot);

  const initial = toQueryFields(timerTick());
  assert.equal(initial.status, 'new');
  assert.equal(initial.levels, '');

  loaded.updateAlertRefreshQuerySnapshot!(snapshot, {
    activeTab: 'activeAlarms',
    filters: { level: ['critical'], state: [] },
    myAlert: false
  });
  const afterLevel = toQueryFields(timerTick());
  assert.equal(
    afterLevel.levels,
    'critical',
    '级别改成 critical 后下一 tick levels=critical'
  );
  assert.equal(afterLevel.status, 'new');

  loaded.updateAlertRefreshQuerySnapshot!(snapshot, {
    activeTab: 'historicalAlarms',
    filters: { level: ['critical'], state: [] },
    myAlert: false
  });
  const afterTab = toQueryFields(timerTick());
  assert.equal(
    afterTab.status,
    'closed',
    '切到 historicalAlarms 后下一 tick status=closed'
  );
  assert.equal(afterTab.levels, 'critical');

  const withExtra = toQueryFields(
    loaded.resolveAlertRefreshQuery!(snapshot, {
      tab: 'activeAlarms',
      filtersConfig: { level: ['error'], state: [] }
    })
  );
  assert.equal(withExtra.status, 'new');
  assert.equal(withExtra.levels, 'error');

  loaded.updateAlertRefreshQuerySnapshot!(snapshot, {
    activeTab: 'historicalAlarms',
    filters: { level: ['critical'], state: [] },
    myAlert: true
  });
  const afterMine = timerTick();
  assert.equal(
    afterMine.myAlert,
    true,
    '勾选我的告警后下一 tick 仍应带 myAlert'
  );
  assert.equal(
    loaded.resolveAlertRefreshQuery!(snapshot, { myAlert: false }).myAlert,
    false,
    '手工刷新 extra.myAlert 覆盖快照'
  );

  const page = readFileSync(pagePath, 'utf8');
  assert.match(
    page,
    /from '\.\/alertRefreshQuery'/,
    '告警页必须使用抽出的查询快照'
  );
  assert.match(
    page,
    /resolveAlertRefreshQuery/,
    '定时与手工刷新必须经 resolveAlertRefreshQuery 读取页签和级别'
  );
  assert.match(
    page,
    /getAssetInsts\('timer'\)/,
    '定时路径仍应无 extra 调用表格刷新'
  );
  assert.match(
    page,
    /getChartData\('timer'\)/,
    '定时路径仍应无 extra 调用分布图刷新'
  );
  assert.doesNotMatch(
    page,
    /extra\?\.tab \|\| activeTab/,
    '源码定时路径不得直接闭包旧 activeTab'
  );
  assert.doesNotMatch(
    page,
    /extra\?\.filtersConfig \|\| filters/,
    '源码定时路径不得直接闭包旧 filters'
  );
  assert.match(page, /alertAbortControllerRef/, '须保留告警列表 abort');
  assert.match(page, /alertRequestIdRef/, '须保留告警列表序号');
  assert.match(page, /chartAbortControllerRef/, '须保留分布图 abort');
  assert.match(page, /chartRequestIdRef/, '须保留分布图序号');

  console.log('log-alert-refresh-query validation passed');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
