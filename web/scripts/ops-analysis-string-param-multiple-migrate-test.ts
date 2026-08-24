import assert from 'node:assert/strict';

import type { UnifiedFilterDefinition } from '../src/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '../src/app/ops-analysis/types/dataSource';
import {
  areNormalizedInputConfigsCompatible,
  migrateFilterBindings,
  migrateParamItemFromStringList,
  migrateUnifiedFilterDefinitions,
  normalizeStringListInputConfig,
  type LegacyUnifiedFilterDefinition,
} from '../src/app/ops-analysis/utils/stringParamMultipleMigrate';

const dynamicSource = {
  type: 'dynamic' as const,
  sourceRef: { type: 'rest_api' as const, value: 'monitor/list_hosts' },
  valueField: 'id',
  labelField: 'name',
};

{
  const { inputConfig, warnings } = normalizeStringListInputConfig({
    inputConfig: {
      control: 'select',
      picker: 'table',
      multiple: false,
      optionsSource: dynamicSource,
    },
  });
  assert.equal(inputConfig?.control, 'select');
  assert.equal(inputConfig && 'picker' in inputConfig ? inputConfig.picker : undefined, 'table');
  assert.equal(inputConfig && 'multiple' in inputConfig ? inputConfig.multiple : undefined, true);
  assert.deepEqual(
    inputConfig && 'optionsSource' in inputConfig ? inputConfig.optionsSource : undefined,
    dynamicSource,
  );
  assert.equal(warnings.length, 0, '保留原配置时不应产生无关 warning');
}

{
  const { inputConfig, warnings } = normalizeStringListInputConfig({});
  assert.deepEqual(inputConfig, {
    control: 'select',
    multiple: true,
    optionsSource: { type: 'static', staticItems: [] },
  });
  assert.equal(warnings.length, 0);
}

{
  const { inputConfig } = normalizeStringListInputConfig({
    options: [{ label: 'A', value: 'a' }],
  });
  assert.equal(inputConfig?.control, 'select');
  assert.equal(inputConfig && 'multiple' in inputConfig ? inputConfig.multiple : undefined, true);
  assert.deepEqual(
    inputConfig && 'optionsSource' in inputConfig ? inputConfig.optionsSource : undefined,
    { type: 'static', staticItems: [{ label: 'A', value: 'a' }] },
  );
}

{
  const { inputConfig, warnings } = normalizeStringListInputConfig({
    inputConfig: { control: 'input' },
  });
  assert.deepEqual(inputConfig, { control: 'input' });
  assert.equal(warnings.length, 0, '旧 stringList 若控件为 input 应保留控件类型');
}

{
  const { inputConfig, warnings } = normalizeStringListInputConfig({
    inputConfig: {
      control: 'select',
      componentSwitch: true,
      optionsSource: { type: 'static', staticItems: [{ label: 'A', value: 'a' }] },
    },
  });
  assert.equal(inputConfig && 'multiple' in inputConfig ? inputConfig.multiple : undefined, true);
  assert.equal(
    inputConfig && 'componentSwitch' in inputConfig ? inputConfig.componentSwitch : undefined,
    undefined,
  );
  assert.ok(
    warnings.some((item) => item.code === 'string_list_component_switch_conflict'),
    'stringList + componentSwitch 必须记录互斥冲突',
  );
}

{
  const param: ParamItem = {
    name: 'instance_ids',
    alias_name: '主机',
    type: 'stringList',
    value: null,
    inputConfig: {
      control: 'select',
      picker: 'table',
      optionsSource: dynamicSource,
    },
  };
  const { param: migrated, warnings } = migrateParamItemFromStringList(param);
  assert.equal(migrated.type, 'string');
  assert.equal(migrated.inputConfig && 'multiple' in migrated.inputConfig
    ? migrated.inputConfig.multiple
    : undefined, true);
  assert.equal(migrated.inputConfig && 'picker' in migrated.inputConfig
    ? migrated.inputConfig.picker
    : undefined, 'table');
  assert.equal(warnings.length, 0);
}

{
  const listSide: LegacyUnifiedFilterDefinition = {
    id: 'instance_ids__stringList',
    key: 'instance_ids',
    name: '主机多选',
    type: 'stringList',
    order: 1,
    enabled: true,
    defaultValue: ['h1', 'h2'],
    inputConfig: {
      control: 'select',
      multiple: true,
      optionsSource: dynamicSource,
    },
  };
  const scalarSide: LegacyUnifiedFilterDefinition = {
    id: 'instance_ids__string',
    key: 'instance_ids',
    name: '主机单选',
    type: 'string',
    order: 0,
    enabled: false,
    defaultValue: 'h0',
    inputConfig: {
      control: 'input',
    },
  };

  const { definitions, values, warnings } = migrateUnifiedFilterDefinitions(
    [scalarSide, listSide],
    {
      [scalarSide.id]: 'h0',
      [listSide.id]: ['h1', 'h2'],
    },
  );

  assert.equal(definitions.length, 1);
  assert.equal(definitions[0].id, 'instance_ids__string');
  assert.equal(definitions[0].type, 'string');
  assert.equal(definitions[0].name, '主机多选');
  assert.deepEqual(definitions[0].defaultValue, ['h1', 'h2']);
  assert.equal(definitions[0].inputConfig && 'multiple' in definitions[0].inputConfig
    ? definitions[0].inputConfig.multiple
    : undefined, true);
  assert.deepEqual(values, { 'instance_ids__string': ['h1', 'h2'] });
  assert.ok(warnings.some((item) => item.code === 'string_list_dual_id_incompatible'));
}

{
  const compatible: LegacyUnifiedFilterDefinition[] = [
    {
      id: 'env__string',
      key: 'env',
      name: '环境',
      type: 'string',
      order: 0,
      enabled: true,
      inputConfig: {
        control: 'select',
        optionsSource: { type: 'static', staticItems: [{ label: 'prod', value: 'prod' }] },
      },
    },
    {
      id: 'env__stringList',
      key: 'env',
      name: '环境多选',
      type: 'stringList',
      order: 1,
      enabled: true,
      inputConfig: {
        control: 'select',
        optionsSource: { type: 'static', staticItems: [{ label: 'prod', value: 'prod' }] },
      },
    },
  ];
  const { warnings } = migrateUnifiedFilterDefinitions(compatible, {});
  assert.ok(!warnings.some((item) => item.code === 'string_list_dual_id_incompatible'));
}

{
  assert.equal(
    areNormalizedInputConfigsCompatible(
      {
        control: 'select',
        optionsSource: {
          type: 'dynamic',
          sourceId: 1,
          valueField: 'id',
          labelField: 'name',
        },
      },
      {
        control: 'select',
        optionsSource: {
          type: 'dynamic',
          sourceId: 1,
          valueField: 'id',
          labelField: 'name',
          // @ts-expect-error intentional extra candidate-set field
          requestParams: { group: 'a' },
        },
      },
    ),
    false,
    '动态选项完整身份应包含会改变候选集的附加字段',
  );
}

{
  const bindings = migrateFilterBindings({
    'instance_ids__stringList': true,
    'instance_ids__string': false,
    'time__timeRange': true,
  });
  assert.deepEqual(bindings, {
    'instance_ids__string': true,
    'time__timeRange': true,
  });
}

{
  const listSide: LegacyLegacyUnifiedFilterDefinition = {
    id: 'instance_ids__stringList',
    key: 'instance_ids',
    name: '主机多选',
    type: 'stringList',
    order: 1,
    enabled: true,
    defaultValue: ['h1', 'h2'],
    inputConfig: {
      control: 'select',
      multiple: true,
      optionsSource: dynamicSource,
    },
  };
  const scalarSide: LegacyLegacyUnifiedFilterDefinition = {
    id: 'instance_ids__string',
    key: 'instance_ids',
    name: '主机单选',
    type: 'string',
    order: 0,
    enabled: false,
    defaultValue: 'h0',
    inputConfig: {
      control: 'input',
    },
  };
  const values = {
    [scalarSide.id]: 'h0' as const,
    [listSide.id]: ['h1', 'h2'] as Array<string>,
  };
  const first = migrateUnifiedFilterDefinitions([scalarSide, listSide], values);
  const second = migrateUnifiedFilterDefinitions([listSide, scalarSide], values);
  assert.deepEqual(first.definitions, second.definitions, '双 ID 两种输入顺序应输出相同 definitions');
  assert.deepEqual(first.values, second.values, '双 ID 两种输入顺序应输出相同 values');
  assert.deepEqual(
    first.warnings.map((item) => item.code).sort(),
    second.warnings.map((item) => item.code).sort(),
  );
}

{
  const listSide: LegacyUnifiedFilterDefinition = {
    id: 'env__stringList',
    key: 'env',
    name: '环境多选',
    type: 'stringList',
    order: 1,
    enabled: true,
    inputConfig: {
      control: 'select',
      componentSwitch: true,
      optionsSource: { type: 'static', staticItems: [{ label: 'prod', value: 'prod' }] },
    },
  };
  const once = migrateUnifiedFilterDefinitions([listSide], {});
  const twice = migrateUnifiedFilterDefinitions(once.definitions, once.values);
  assert.deepEqual(twice.definitions, once.definitions, '迁移应幂等');
  assert.deepEqual(twice.values, once.values);
  assert.equal(twice.warnings.length, 0, '第二次迁移不得重复产生冲突 warning');
  assert.ok(once.warnings.some((item) => item.code === 'string_list_component_switch_conflict'));
}

{
  const nestedSource = {
    type: 'dynamic' as const,
    sourceRef: { type: 'rest_api' as const, value: 'monitor/list_hosts' },
    valueField: 'id',
    labelField: 'name',
    requestParams: { group: 'a' },
  };
  const input = {
    name: 'hosts',
    type: 'stringList' as const,
    value: null,
    inputConfig: {
      control: 'select' as const,
      picker: 'table' as const,
      componentSwitch: true,
      optionsSource: nestedSource,
    },
  };
  const before = JSON.parse(JSON.stringify(input));
  const { param } = migrateParamItemFromStringList(input as any);
  assert.deepEqual(input, before, '迁移不得修改输入对象');
  assert.notEqual(
    (param.inputConfig as any)?.optionsSource,
    input.inputConfig.optionsSource,
    '迁移结果不得与输入共享 optionsSource 引用',
  );
  assert.deepEqual((param.inputConfig as any)?.optionsSource, nestedSource);
}

{
  assert.equal(
    areNormalizedInputConfigsCompatible(
      {
        control: 'select',
        optionsSource: {
          type: 'dynamic',
          sourceId: 1,
          valueField: 'id',
          labelField: 'name',
          requestParams: { b: 2, a: 1 },
        } as any,
      },
      {
        control: 'select',
        optionsSource: {
          labelField: 'name',
          valueField: 'id',
          type: 'dynamic',
          sourceId: 1,
          requestParams: { a: 1, b: 2 },
        } as any,
      },
    ),
    true,
    '完整 optionsSource 身份比较不应受对象 key 顺序影响',
  );
}

console.log('ops analysis string param multiple migrate tests passed');
