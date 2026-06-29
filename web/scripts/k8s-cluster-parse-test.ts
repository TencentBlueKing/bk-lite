import assert from 'node:assert/strict';

import { latestScalar, phaseCount } from '../src/app/monitor/dashboards/objects/k8s-cluster/parse';

// 回归:gap 检测会在 query_range 矩阵尾部插入 null 标记点。latestScalar(经 lastValue)若直接取
// 最后一个数组元素,会拿到 null → Number(null)=0 → K8s 集群仪表盘 KPI 卡一律显示 0。
// 修复后跳过尾部 null,取最后一个有效采样值。
const withTrailingGapNull = {
  data: {
    result: [
      {
        metric: {},
        values: [
          [1000, '1'],
          [1009.2, null],
          [1010, '1'],
          [1018.2, null],
        ] as Array<[number, string]>,
      },
    ],
  },
};
assert.equal(latestScalar(withTrailingGapNull), 1, '尾部 gap-null 应被跳过,取最后有效值 1');

// 多个尾部 null 也应一路回退到有效值
const multipleTrailingNulls = {
  data: { result: [{ metric: {}, values: [[1, '7'], [2, null], [3, null], [4, null]] as Array<[number, string]> }] },
};
assert.equal(latestScalar(multipleTrailingNulls), 7, '连续尾部 null 应回退到 7');

// 正常无 null:取最后值
const normal = {
  data: { result: [{ metric: {}, values: [[1, '5'], [2, '6']] as Array<[number, string]> }] },
};
assert.equal(latestScalar(normal), 6);

// 全 null → 0
const allNull = {
  data: { result: [{ metric: {}, values: [[1, null], [2, null]] as Array<[number, string]> }] },
};
assert.equal(latestScalar(allNull), 0, '全 null 序列应为 0');

// 空结果 → 0
assert.equal(latestScalar({ data: { result: [] } }), 0);
assert.equal(latestScalar(null), 0);

// phaseCount 依赖 lastValue,by(phase) 结果尾部 null 也应跳过
const podPhase = {
  data: {
    result: [
      { metric: { phase: 'Running' }, values: [[1, '7'], [2, null]] as Array<[number, string]> },
      { metric: { phase: 'Pending' }, values: [[1, '0']] as Array<[number, string]> },
    ],
  },
};
assert.equal(phaseCount(podPhase, 'Running'), 7, 'Running 计数应跳过尾部 null 取 7');
assert.equal(phaseCount(podPhase, 'Failed'), 0, '缺失 phase 计数为 0');

console.log('k8s-cluster-parse-test: all assertions passed');
