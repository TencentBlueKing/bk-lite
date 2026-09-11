import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import { applyEdgeConfigConfirm } from '../src/app/ops-analysis/(pages)/view/topology/utils/edgeConfigConfirm';

const oldSourceInterface = { type: 'existing' as const, value: 'eth0' };
const oldTargetInterface = { type: 'existing' as const, value: 'eth1' };
const newSourceInterface = { type: 'custom' as const, value: 'GigabitEthernet0/1' };
const newTargetInterface = { type: 'custom' as const, value: 'GigabitEthernet0/2' };
const vertices = [{ x: 10, y: 20 }];

const previousEdgeData = {
  id: 'edge-1',
  lineType: 'network_line' as const,
  lineName: '',
  arrowDirection: 'single' as const,
  styleConfig: {
    lineColor: '#8c8c8c',
    lineWidth: 1,
    lineStyle: 'line' as const,
    enableAnimation: false,
  },
  sourceNode: { id: 'n1', name: '节点1' },
  targetNode: { id: 'n2', name: '节点2' },
  sourceInterface: oldSourceInterface,
  targetInterface: oldTargetInterface,
};

const confirmedValues = {
  ...previousEdgeData,
  sourceInterface: newSourceInterface,
  targetInterface: newTargetInterface,
};

const setDataPayload = applyEdgeConfigConfirm(
  previousEdgeData,
  confirmedValues,
  vertices,
);
const setCurrentEdgeDataPayload = applyEdgeConfigConfirm(
  previousEdgeData,
  confirmedValues,
  vertices,
);

assert.deepEqual(
  setDataPayload.sourceInterface,
  newSourceInterface,
  'network_line 确认后 setData 载荷应含新 sourceInterface',
);
assert.deepEqual(
  setDataPayload.targetInterface,
  newTargetInterface,
  'network_line 确认后 setData 载荷应含新 targetInterface',
);
assert.deepEqual(
  setCurrentEdgeDataPayload.sourceInterface,
  newSourceInterface,
  'setCurrentEdgeData 应同步含新 sourceInterface',
);
assert.deepEqual(
  setCurrentEdgeDataPayload.targetInterface,
  newTargetInterface,
  'setCurrentEdgeData 应同步含新 targetInterface',
);
assert.notDeepEqual(
  setDataPayload.sourceInterface,
  oldSourceInterface,
  '确认后不得残留旧 sourceInterface',
);
assert.notDeepEqual(
  setDataPayload.targetInterface,
  oldTargetInterface,
  '确认后不得残留旧 targetInterface',
);

const legacyEdge = {
  id: 'edge-legacy',
  lineType: 'network_line' as const,
  sourceNode: { id: 'n1', name: '节点1' },
  targetNode: { id: 'n2', name: '节点2' },
};
const legacyConfirm = applyEdgeConfigConfirm(
  legacyEdge,
  {
    lineType: 'network_line',
    lineName: '',
    styleConfig: previousEdgeData.styleConfig,
  },
  [],
);
assert.equal(
  legacyConfirm.sourceInterface,
  undefined,
  '缺接口的旧边确认未提交接口时应保持 undefined',
);
assert.equal(
  legacyConfirm.targetInterface,
  undefined,
  '缺接口的旧边确认未提交接口时应保持 undefined',
);

const root = process.cwd();
const hookSource = fs.readFileSync(
  path.join(
    root,
    'src/app/ops-analysis/(pages)/view/topology/hooks/useGraphInteractions.ts',
  ),
  'utf8',
);

assert.match(
  hookSource,
  /import \{ applyEdgeConfigConfirm \} from '\.\.\/utils\/edgeConfigConfirm'/,
  'useGraphInteractions 应使用抽出的 applyEdgeConfigConfirm',
);

const confirmFn = hookSource.match(
  /const handleEdgeConfigConfirm = useCallback\([\s\S]*?\},\s*\[[^\]]*\]\s*\);/,
)?.[0];
assert.ok(confirmFn, '应能定位 handleEdgeConfigConfirm');
assert.match(
  confirmFn,
  /applyEdgeConfigConfirm/,
  'handleEdgeConfigConfirm 应调用抽出函数',
);
assert.doesNotMatch(
  confirmFn,
  /edge\.setData\(\{/,
  'setData 不得再手写漏接口字段的对象字面量',
);
assert.doesNotMatch(
  confirmFn,
  /setCurrentEdgeData\(\{/,
  'setCurrentEdgeData 不得再手写漏接口字段的对象字面量',
);

console.log('ops topology edge interface validation passed');
