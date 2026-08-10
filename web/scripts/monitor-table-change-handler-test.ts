import assert from 'node:assert/strict';
import { applyTableChangeHandler } from '../src/app/monitor/hooks/integration/tableChangeHandler';

const options = [
  {
    value: 'node-1',
    name: '生产节点 A',
    label: '生产节点 A (10.0.0.1)'
  },
  {
    value: 'node-2',
    name: '生产节点 B',
    label: '生产节点 B (10.0.0.2)'
  }
];
const optionFieldHandler = {
  type: 'option_field',
  source_field: 'name',
  target_field: 'instance_name'
} as const;

assert.equal(
  applyTableChangeHandler(
    { instance_name: '自定义名称' },
    'node-1',
    options,
    optionFieldHandler
  ).instance_name,
  '生产节点 A',
  '应使用节点真实名称，而不是包含 IP 的展示标签'
);

assert.equal(
  applyTableChangeHandler(
    { instance_name: '生产节点 A' },
    'node-2',
    options,
    optionFieldHandler
  ).instance_name,
  '生产节点 B',
  '重新选择节点时应更新实例名称默认值'
);

assert.equal(
  applyTableChangeHandler(
    { instance_name: '保留名称' },
    undefined,
    options,
    optionFieldHandler
  ).instance_name,
  '保留名称',
  '清空节点时不应覆盖用户填写的实例名称'
);

assert.equal(
  applyTableChangeHandler(
    { instance_name: '保留名称' },
    'missing',
    options,
    optionFieldHandler
  ).instance_name,
  '保留名称',
  '找不到节点选项时不应覆盖实例名称'
);

assert.equal(
  applyTableChangeHandler(
    { instance_name: '保留名称' },
    'node-without-name',
    [{ value: 'node-without-name', label: '仅展示标签' }],
    optionFieldHandler
  ).instance_name,
  '保留名称',
  '节点没有真实名称时不应使用展示标签兜底'
);

assert.deepEqual(
  applyTableChangeHandler({ host: '10.0.0.1' }, '10.0.0.1', [], {
    type: 'simple',
    source_fields: ['host'],
    target_field: 'instance_name'
  }),
  { host: '10.0.0.1', instance_name: '10.0.0.1' },
  '既有 simple 处理器行为应保持不变'
);

console.log('monitor table change handler tests passed');
