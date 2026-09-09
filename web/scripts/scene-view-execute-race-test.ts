import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLatestRequestGuard } from '../src/context/latestRequestGuard.ts';
import type { LatestRequestGuard } from '../src/context/latestRequestGuard.ts';
import type { SceneExecuteResult } from '../src/app/cmdb/api/sceneView.ts';

interface ModelPager {
  page: number;
  pageSize: number;
}

interface CommitFns {
  beginSceneViewExecute: (guard: LatestRequestGuard) => number;
  commitSceneViewExecuteSuccess: (
    guard: LatestRequestGuard,
    requestId: number,
    apply: () => void,
  ) => boolean;
  commitSceneViewExecuteSettled: (
    guard: LatestRequestGuard,
    requestId: number,
    settle: () => void,
  ) => boolean;
}

interface ViewState {
  result: SceneExecuteResult | null;
  modelPagers: Record<string, ModelPager>;
  loadingScope: 'all' | string | null;
}

const here = dirname(fileURLToPath(import.meta.url));
const pagePath = resolve(here, '../src/app/cmdb/(pages)/views/scene/page.tsx');
const utilPath = resolve(
  here,
  '../src/app/cmdb/(pages)/views/scene/sceneViewExecuteRequest.ts',
);
const localePath = resolve(here, '../src/app/cmdb/locales/zh.json');
const menuPath = resolve(here, '../src/app/cmdb/constants/menu.json');

const PAGE_COPY = {
  menuViews: '视图',
  menuTagView: '标签视图',
  pageTitle: '标签视图',
  createButton: '新建视图',
  emptyPick: '从左侧打开视图，或新建一个',
};

async function loadCommitFns(): Promise<CommitFns> {
  let loaded: Partial<CommitFns> = {};
  try {
    loaded = await import(
      '../src/app/cmdb/(pages)/views/scene/sceneViewExecuteRequest.ts'
    );
  } catch {
    // RED：提交函数尚未抽出。
  }

  assert.equal(typeof loaded.beginSceneViewExecute, 'function', '应抽出 beginSceneViewExecute');
  assert.equal(
    typeof loaded.commitSceneViewExecuteSuccess,
    'function',
    '应抽出 commitSceneViewExecuteSuccess',
  );
  assert.equal(
    typeof loaded.commitSceneViewExecuteSettled,
    'function',
    '应抽出 commitSceneViewExecuteSettled',
  );

  return loaded as CommitFns;
}

function resultFor(view: string, modelId = 'host'): SceneExecuteResult {
  return {
    total: 1,
    models: [
      {
        model_id: modelId,
        count: 1,
        insts: [{ inst_name: view, inst_uuid: view }],
      },
    ],
  };
}

function mergePagers(
  pagers: Record<string, ModelPager>,
  data: SceneExecuteResult,
): Record<string, ModelPager> {
  const next = { ...pagers };
  for (const item of data.models || []) {
    if (!next[item.model_id]) {
      next[item.model_id] = { page: 1, pageSize: 20 };
    }
  }
  return next;
}

function createExecuteSession(fns: CommitFns) {
  const guard = createLatestRequestGuard();
  const state: ViewState = {
    result: null,
    modelPagers: {},
    loadingScope: null,
  };

  const start = (scope: 'all' | string) => {
    const requestId = fns.beginSceneViewExecute(guard);
    state.loadingScope = scope;
    return requestId;
  };

  const succeed = (
    requestId: number,
    data: SceneExecuteResult,
    pagers: Record<string, ModelPager> = {},
  ) => {
    const applied = fns.commitSceneViewExecuteSuccess(guard, requestId, () => {
      state.result = data;
      state.modelPagers = mergePagers(pagers, data);
    });
    fns.commitSceneViewExecuteSettled(guard, requestId, () => {
      state.loadingScope = null;
    });
    return applied;
  };

  const fail = (requestId: number) => {
    return fns.commitSceneViewExecuteSettled(guard, requestId, () => {
      state.loadingScope = null;
    });
  };

  const switchView = () => {
    guard.invalidate();
    state.result = null;
    state.modelPagers = {};
  };

  return {
    getState: () => state,
    start,
    succeed,
    fail,
    switchView,
    unmount: () => guard.invalidate(),
  };
}

function assertPageUsesGeneration(source: string) {
  assert.match(
    source,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'page 必须复用 @/context/latestRequestGuard，不得复制新 guard',
  );
  assert.match(source, /createLatestRequestGuard/, 'page 必须创建 latest request guard');
  assert.match(
    source,
    /from ['"]\.\/sceneViewExecuteRequest['"]/,
    'page 必须调用抽出的 sceneViewExecuteRequest',
  );
  assert.match(source, /beginSceneViewExecute\(/, 'runExecute 必须按单调序号 begin');
  assert.match(
    source,
    /commitSceneViewExecuteSuccess\(/,
    '成功响应必须经 commitSceneViewExecuteSuccess 提交',
  );
  assert.match(
    source,
    /commitSceneViewExecuteSettled\(/,
    '结束 loading 必须经 commitSceneViewExecuteSettled 提交',
  );
  assert.match(source, /requestGuard\.invalidate\(\)/, '切换 selectedId 与卸载必须 invalidate');

  const runExecuteFn =
    source.match(/const runExecute = useCallback\([\s\S]*?(?=\n  useEffect)/)?.[0] || '';
  assert.ok(runExecuteFn.includes('const runExecute'), '必须能定位 runExecute');
  assert.match(runExecuteFn, /beginSceneViewExecute\(/, 'runExecute 必须 begin 新代次');
  assert.match(
    runExecuteFn,
    /commitSceneViewExecuteSuccess\(/,
    'runExecute await 后必须按序号提交 result/pagers',
  );
  assert.match(
    runExecuteFn,
    /commitSceneViewExecuteSettled\(/,
    'runExecute finally 必须按序号提交 loading',
  );
  assert.match(
    runExecuteFn,
    /executeSceneView\(\s*id\s*,/,
    '不得改 executeSceneView 调用签名',
  );
  assert.match(
    runExecuteFn,
    /pagination:\s*toPaginationPayload\(pagers\)/,
    'executeSceneView 仍须传 pagination',
  );
  assert.match(
    runExecuteFn,
    /searches:\s*toSearchPayload\(searches\)/,
    'executeSceneView 仍须传 searches',
  );

  const invalidates = source.match(/requestGuard\.invalidate\(\)/g);
  assert.ok(
    invalidates && invalidates.length >= 1,
    '切换 selectedId 或卸载必须 invalidate',
  );

  assert.match(source, /setResult\(null\)/, '切换视图时必须清理旧结果');
  assert.match(source, /t\('SceneView\.title'\)/, '页头必须仍用 SceneView.title');
  assert.match(source, /t\('SceneView\.create'\)/, '按钮必须仍用 SceneView.create');
  assert.match(source, /t\('SceneView\.emptyPick'\)/, '空态必须仍用 SceneView.emptyPick');

  assert.doesNotMatch(
    source,
    /function createLatestRequestGuard|const createLatestRequestGuard\s*=/,
    '不得在 page 内复制一套序号 guard',
  );

  const aside = source.match(/<aside[\s\S]*?<\/aside>/)?.[0] || '';
  assert.ok(aside.includes('<aside'), '必须能定位侧栏');
  assert.doesNotMatch(aside, /\bdisabled\b/, '不得把禁用侧栏当唯一修复');
}

function assertCopy() {
  const menu = JSON.parse(readFileSync(menuPath, 'utf8')) as {
    zh: Array<{ title: string; url?: string; children?: Array<{ title: string; name: string }> }>;
  };
  const views = menu.zh.find((item) => item.title === PAGE_COPY.menuViews);
  assert.ok(views, '菜单必须有「视图」');
  const tagView = (views?.children || []).find((item) => item.name === 'asset_views_scene');
  assert.equal(tagView?.title, PAGE_COPY.menuTagView, '菜单「视图」下必须是「标签视图」');

  const locale = JSON.parse(readFileSync(localePath, 'utf8')) as {
    SceneView: { title: string; create: string; emptyPick: string };
  };
  assert.equal(locale.SceneView.title, PAGE_COPY.pageTitle);
  assert.equal(locale.SceneView.create, PAGE_COPY.createButton);
  assert.equal(locale.SceneView.emptyPick, PAGE_COPY.emptyPick);
}

async function main() {
  assertCopy();

  const fns = await loadCommitFns();

  const viewRace = createExecuteSession(fns);
  const staleView = viewRace.start('all');
  viewRace.switchView();
  const latestView = viewRace.start('all');
  assert.equal(viewRace.getState().result, null, '切到视图 B 必须先清掉 A 的结果');
  const bApplied = viewRace.succeed(latestView, resultFor('view-B'), {});
  const aApplied = viewRace.succeed(staleView, resultFor('view-A'), {});
  assert.equal(bApplied, true, '当前视图 B 的成功必须可写');
  assert.equal(aApplied, false, 'A 后发先至不得覆盖 B');
  assert.equal(
    viewRace.getState().result?.models[0]?.insts[0]?.inst_name,
    'view-B',
    '侧栏切到 B 后旧 A 响应不得覆盖 B 的 result',
  );
  assert.equal(viewRace.getState().loadingScope, null, '当前代次结束后才清 loading');

  const pageRace = createExecuteSession(fns);
  const stalePage = pageRace.start('host');
  const latestPage = pageRace.start('host');
  pageRace.succeed(latestPage, resultFor('page-2'), {
    host: { page: 2, pageSize: 20 },
  });
  pageRace.succeed(stalePage, resultFor('page-1'), {
    host: { page: 1, pageSize: 20 },
  });
  assert.equal(
    pageRace.getState().result?.models[0]?.insts[0]?.inst_name,
    'page-2',
    '同视图翻页乱序：旧页结果不得覆盖新页',
  );
  assert.deepEqual(
    pageRace.getState().modelPagers.host,
    { page: 2, pageSize: 20 },
    '同视图翻页乱序：pagers 必须属于最新请求',
  );

  const filterRace = createExecuteSession(fns);
  const staleFilter = filterRace.start('host');
  const latestFilter = filterRace.start('host');
  filterRace.succeed(latestFilter, resultFor('filter-prod'), {
    host: { page: 1, pageSize: 20 },
  });
  filterRace.succeed(staleFilter, resultFor('filter-all'), {
    host: { page: 1, pageSize: 20 },
  });
  assert.equal(
    filterRace.getState().result?.models[0]?.insts[0]?.inst_name,
    'filter-prod',
    '同视图筛选乱序：旧筛选结果不得覆盖新筛选',
  );

  const lateFail = createExecuteSession(fns);
  const staleFail = lateFail.start('all');
  const latestOk = lateFail.start('all');
  assert.equal(lateFail.getState().loadingScope, 'all', '新请求必须持有 loading');
  const staleSettled = lateFail.fail(staleFail);
  assert.equal(staleSettled, false, '旧失败晚到不得提交 settle');
  assert.equal(lateFail.getState().loadingScope, 'all', '旧失败晚到不得清掉新 loading');
  lateFail.succeed(latestOk, resultFor('current-ok'));
  assert.equal(
    lateFail.getState().result?.models[0]?.insts[0]?.inst_name,
    'current-ok',
    '旧失败晚到不得覆盖当前成功',
  );
  assert.equal(lateFail.getState().loadingScope, null);

  const unmounted = createExecuteSession(fns);
  const lateSuccess = unmounted.start('all');
  unmounted.unmount();
  assert.equal(
    unmounted.succeed(lateSuccess, resultFor('after-unmount')),
    false,
    '卸载后旧成功不得提交',
  );
  assert.equal(unmounted.getState().result, null, '卸载后旧成功不得写回 result');
  assert.equal(unmounted.getState().loadingScope, 'all', '卸载后旧成功不得改 loading');
  assert.equal(unmounted.fail(lateSuccess), false, '卸载后旧失败不得清 loading');

  const currentOk = createExecuteSession(fns);
  const currentGen = currentOk.start('all');
  assert.equal(currentOk.succeed(currentGen, resultFor('current')), true);
  assert.equal(currentOk.getState().result?.models[0]?.insts[0]?.inst_name, 'current');
  assert.equal(currentOk.getState().loadingScope, null);

  const pageSource = readFileSync(pagePath, 'utf8');
  const utilSource = readFileSync(utilPath, 'utf8');
  assertPageUsesGeneration(pageSource);
  assert.match(
    utilSource,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'sceneViewExecuteRequest 必须复用 LatestRequestGuard 类型',
  );
  assert.doesNotMatch(
    utilSource,
    /createLatestRequestGuard\s*=|function createLatestRequestGuard/,
    'sceneViewExecuteRequest 不得复制一套序号 guard',
  );
  assert.match(utilSource, /commitIfCurrent/, '抽出模块必须经 commitIfCurrent 提交');

  console.log('scene view execute race test passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
