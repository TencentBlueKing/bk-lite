import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  buildCollectorTaskNodesPageQuery,
  resolveCollectorTaskNodesPage
} from '../src/app/node-manager/(pages)/cloudregion/node/operationProgress/collectorTaskNodesPage.ts';

const PAGE_SIZE = 20;
const TOTAL_NODES = 21;

const makeItems = (count: number, start = 1) =>
  Array.from({ length: count }, (_, index) => ({
    node_id: `node-${start + index}`,
    status: 'running'
  }));

const simulateCollectorPoll = (pagination: {
  current: number;
  pageSize: number;
}) => buildCollectorTaskNodesPageQuery(pagination);

const simulateControllerRequest = () => ({});

const pageOneQuery = buildCollectorTaskNodesPageQuery({
  current: 1,
  pageSize: PAGE_SIZE
});
assert.equal(pageOneQuery.page, 1, '21 台且 page_size=20 时第一页请求必须带 page=1');
assert.equal(
  pageOneQuery.page_size,
  PAGE_SIZE,
  '21 台且 page_size=20 时请求必须带 page_size=20'
);

const pageOneResolved = resolveCollectorTaskNodesPage({
  items: makeItems(20),
  count: TOTAL_NODES
});
assert.equal(pageOneResolved.items.length, 20, '当前页 items 仍是 20');
assert.equal(
  pageOneResolved.total,
  TOTAL_NODES,
  'count=21 时表格 total 必须是 21，不能用当前页 items.length'
);

const pageTwoQuery = buildCollectorTaskNodesPageQuery({
  current: 2,
  pageSize: PAGE_SIZE
});
assert.equal(pageTwoQuery.page, 2, '切到第 2 页时请求必须带 page=2');
assert.equal(pageTwoQuery.page_size, PAGE_SIZE);

const pageTwoResolved = resolveCollectorTaskNodesPage({
  items: makeItems(1, 21),
  count: TOTAL_NODES
});
assert.equal(pageTwoResolved.items.length, 1);
assert.equal(pageTwoResolved.total, TOTAL_NODES);

const pollWhileOnPageTwo = simulateCollectorPoll({
  current: 2,
  pageSize: PAGE_SIZE
});
assert.equal(
  pollWhileOnPageTwo.page,
  2,
  '轮询必须保持当前页，不能回到第 1 页'
);

const oversizedQuery = buildCollectorTaskNodesPageQuery({
  current: 1,
  pageSize: 501
});
assert.equal(
  oversizedQuery.page_size,
  500,
  '不得超过后端 page_size 上限 500'
);

const controllerBody = simulateControllerRequest();
assert.equal(
  Object.prototype.hasOwnProperty.call(controllerBody, 'page'),
  false,
  '控制器路径不发 page'
);
assert.equal(
  Object.prototype.hasOwnProperty.call(controllerBody, 'page_size'),
  false,
  '控制器路径不发 page_size'
);

const apiSource = readFileSync(
  resolve(process.cwd(), 'src/app/node-manager/api/useNodeApi.ts'),
  'utf8'
);
const collectorInstallFn = apiSource.slice(
  apiSource.indexOf('const getCollectorNodes'),
  apiSource.indexOf('const getCollectorOperationNodes')
);
const collectorOperationFn = apiSource.slice(
  apiSource.indexOf('const getCollectorOperationNodes'),
  apiSource.indexOf('const batchBindCollector')
);
const controllerFn = apiSource.slice(
  apiSource.indexOf('const getControllerNodes'),
  apiSource.indexOf('const getCollectorNodes')
);

assert.match(
  collectorInstallFn,
  /page_size/,
  'getCollectorNodes 必须把 page_size 放进 POST body'
);
assert.match(
  collectorOperationFn,
  /page_size/,
  'getCollectorOperationNodes 必须把 page_size 放进 POST body'
);
assert.doesNotMatch(
  controllerFn,
  /page_size/,
  'getControllerNodes 不得发分页参数'
);

const progressSource = readFileSync(
  resolve(
    process.cwd(),
    'src/app/node-manager/(pages)/cloudregion/node/operationProgress/index.tsx'
  ),
  'utf8'
);
assert.match(
  progressSource,
  /buildCollectorTaskNodesPageQuery/,
  'OperationProgress 必须用抽出模块构造当前页查询'
);
assert.match(
  progressSource,
  /resolveCollectorTaskNodesPage/,
  'OperationProgress 必须用抽出模块解析 items+count'
);
assert.match(
  progressSource,
  /pagination=\{isControllerOperation \? undefined : pagination\}/,
  '仅组件安装/启停把 pagination 传给 CustomTable'
);

console.log('node operation progress pagination tests passed');
