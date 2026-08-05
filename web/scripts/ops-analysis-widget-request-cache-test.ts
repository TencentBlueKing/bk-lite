import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  getOrCreateInflightWidgetRequest,
} from '../src/app/ops-analysis/utils/widgetRequestCache';
import {
  createWidgetRequestHistory,
  decideWidgetRequest,
  type WidgetRequestSnapshot,
} from '../src/app/ops-analysis/utils/widgetDataTransform';

const main = async () => {
  const rendererSource = readFileSync(
    fileURLToPath(new URL('../src/app/ops-analysis/components/widgetDataRenderer.tsx', import.meta.url)),
    'utf8',
  );
  assert.doesNotMatch(
    rendererSource,
    /getCachedWidgetRequest|setWidgetRequestSuccessCache|setRawData\(cached\.rawData\)/,
    '切换画布时不得回填上一次挂载的成功结果',
  );

  const current: WidgetRequestSnapshot = {
    requestEnabled: true,
    requestSignature: 'same-signature',
    hasRequestParams: true,
    hasRequestKey: true,
    filterSearchVersion: 0,
    namespaceSearchVersion: 0,
    reloadVersion: '0',
    tableQueryKey: '',
    hasEnabledFilterBindings: false,
    widgetUsesNamespace: false,
    isTableLikeChart: false,
  };
  const decision = decideWidgetRequest({
    history: createWidgetRequestHistory(current),
    current,
  });
  assert.equal(decision.shouldFetch, true, '重新挂载必须请求当前画布数据');

  const filterOnlyDecision = decideWidgetRequest({
    history: decision.nextHistory,
    current: {
      ...current,
      filterSearchVersion: 1,
      widgetUsesNamespace: true,
    },
  });
  assert.equal(
    filterOnlyDecision.shouldFetch,
    false,
    '未绑定全局筛选的组件不应因搜索重新请求',
  );

  const screenQueryStateSource = readFileSync(
    fileURLToPath(
      new URL(
        '../src/app/ops-analysis/hooks/useOpsAnalysisQueryState.ts',
        import.meta.url,
      ),
    ),
    'utf8',
  );
  assert.match(
    screenQueryStateSource,
    /const namespaceChanged = appliedNamespaceId !== namespaceId;/,
    '大屏搜索必须区分筛选变化与命名空间变化',
  );
  assert.match(
    screenQueryStateSource,
    /if \(namespaceChanged\) \{\s*setNamespaceSearchVersion/,
    '命名空间未变化时不得递增命名空间刷新版本',
  );

  const screenPageSource = readFileSync(
    fileURLToPath(
      new URL(
        '../src/app/ops-analysis/(pages)/view/screen/index.tsx',
        import.meta.url,
      ),
    ),
    'utf8',
  );
  assert.equal(
    screenPageSource.match(/<ScreenCanvas/g)?.length,
    1,
    '全屏切换必须复用同一个大屏画布实例',
  );
  assert.match(
    screenPageSource,
    /const currentViewConfigItem = useMemo(?:<[^>]+>)?\([\s\S]*?\[currentConfigItem\],[\s\S]*?item=\{currentViewConfigItem\}/,
    '大屏组件配置抽屉必须复用稳定的 item 引用，避免切换数据源时被重新初始化',
  );

  const screenCanvasSource = readFileSync(
    fileURLToPath(
      new URL(
        '../src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx',
        import.meta.url,
      ),
    ),
    'utf8',
  );
  assert.doesNotMatch(
    screenCanvasSource,
    /if \(!editMode \|\| fullscreen\)/,
    '编辑状态切换不得替换组件宿主类型',
  );
  assert.match(
    screenCanvasSource,
    /const editable = editMode && !fullscreen;[\s\S]*editable=\{editable\}/,
    '同一个组件宿主只应按状态启停编辑交互',
  );

  const screenWidgetFrameSource = readFileSync(
    fileURLToPath(
      new URL(
        '../src/app/ops-analysis/(pages)/view/screen/components/screenWidgetFrame.tsx',
        import.meta.url,
      ),
    ),
    'utf8',
  );
  assert.match(
    screenWidgetFrameSource,
    /<div key="body" className="screen-widget-frame__body">/,
    '编辑操作栏显隐时必须保留组件正文节点身份',
  );

  let requestCount = 0;
  const createRequest = async () => {
    requestCount += 1;
    return 'latest';
  };
  const [first, second] = await Promise.all([
    getOrCreateInflightWidgetRequest('same', createRequest),
    getOrCreateInflightWidgetRequest('same', createRequest),
  ]);
  assert.deepEqual([first, second], ['latest', 'latest']);
  assert.equal(requestCount, 1);

  console.log('ops analysis widget request coordination tests passed');
};

void main();
