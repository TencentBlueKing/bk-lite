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

const processNodeHandler = {
  type: 'option_then_combine',
  source_field: 'label',
  stash_field: 'node_label',
  source_fields: ['process_name', 'node_label'],
  separator: '-',
  target_field: 'instance_name'
} as const;

const processNameHandler = {
  type: 'combine',
  source_fields: ['process_name', 'node_label'],
  separator: '-',
  target_field: 'instance_name'
} as const;

const afterNodeOnly = applyTableChangeHandler(
  { process_name: '' },
  'node-1',
  options,
  processNodeHandler
);
assert.equal(
  afterNodeOnly.node_label,
  '生产节点 A (10.0.0.1)',
  '选节点时应暂存节点 label'
);
assert.equal(
  afterNodeOnly.instance_name,
  '生产节点 A (10.0.0.1)',
  '仅选节点时实例名应为节点 label，无多余分隔符'
);

assert.equal(
  applyTableChangeHandler(
    { ...afterNodeOnly, process_name: 'nginx' },
    'nginx',
    [],
    processNameHandler
  ).instance_name,
  'nginx-生产节点 A (10.0.0.1)',
  '先选节点再填进程名时应拼接为 进程名-节点label'
);

assert.equal(
  applyTableChangeHandler(
    { process_name: 'nginx' },
    'node-1',
    options,
    processNodeHandler
  ).instance_name,
  'nginx-生产节点 A (10.0.0.1)',
  '先进程名再选节点时应拼接为 进程名-节点label'
);

assert.equal(
  applyTableChangeHandler(
    { host: 'db.example.com', port: '' },
    '',
    [],
    {
      type: 'combine',
      source_fields: ['host', 'port'],
      separator: ':',
      target_field: 'instance_name'
    }
  ).instance_name,
  'db.example.com',
  'combine 应跳过空段，避免多余分隔符'
);

console.log('monitor table change handler tests passed');
