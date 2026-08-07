import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { validateParams } from '../src/app/ops-analysis/(pages)/settings/dataSource/operateModalUtils';
import {
  getDataSourceFormParamInitialValue,
  processDataSourceFormParamsForSubmit,
} from '../src/app/ops-analysis/utils/dataSourceFormParams';
import { processDataSourceParams } from '../src/app/ops-analysis/utils/widgetDataTransform';
import type { ParamItem } from '../src/app/ops-analysis/types/dataSource';

const numberParam: ParamItem = {
  id: 'limit-param',
  name: 'limit',
  alias_name: '返回条数',
  type: 'number',
  filterType: 'params',
  value: 10,
};

assert.equal(
  processDataSourceFormParamsForSubmit({ limit: null }, [numberParam])[0].value,
  null,
  '显式清空数字参数后不能回退到数据源默认值',
);

assert.deepEqual(
  processDataSourceParams({
    sourceParams: [{ ...numberParam, value: null }],
    userParams: { limit: null },
  }),
  {},
  '空的可配置参数不应出现在请求载荷中',
);

const stringParam: ParamItem = {
  id: 'model-param',
  name: 'model_id',
  alias_name: '模型 ID',
  type: 'string',
  filterType: 'params',
  value: 'host',
};
const booleanParam: ParamItem = {
  id: 'enabled-param',
  name: 'enabled',
  alias_name: '是否启用',
  type: 'boolean',
  filterType: 'params',
  value: true,
};
const timeRangeParam: ParamItem = {
  id: 'time-param',
  name: 'time',
  alias_name: '时间范围',
  type: 'timeRange',
  filterType: 'filter',
  value: 10080,
};

assert.equal(
  processDataSourceFormParamsForSubmit({ model_id: '' }, [stringParam])[0].value,
  null,
  '清空字符串参数后必须保存为 null',
);
assert.equal(
  processDataSourceFormParamsForSubmit({ enabled: null }, [booleanParam])[0].value,
  null,
  '清空布尔参数后必须保存为 null',
);
assert.equal(
  processDataSourceFormParamsForSubmit({ enabled: false }, [booleanParam])[0].value,
  false,
  '布尔 false 是有效值，不能按空值处理',
);
assert.equal(
  processDataSourceFormParamsForSubmit({ limit: 0 }, [numberParam])[0].value,
  0,
  '数字 0 是有效值，不能按空值处理',
);
assert.equal(
  processDataSourceFormParamsForSubmit({ time: null }, [timeRangeParam])[0].value,
  null,
  '清空时间范围后必须保存为 null',
);

assert.equal(getDataSourceFormParamInitialValue({ ...booleanParam, value: null }), null);
assert.equal(getDataSourceFormParamInitialValue({ ...booleanParam, value: false }), false);
assert.equal(getDataSourceFormParamInitialValue({ ...timeRangeParam, value: null }), null);
assert.equal(getDataSourceFormParamInitialValue({ ...timeRangeParam, value: undefined }), 10080);

assert.deepEqual(
  processDataSourceParams({
    sourceParams: [
      { ...stringParam, value: null },
      { ...booleanParam, value: null },
      { ...timeRangeParam, value: null },
      { ...numberParam, value: 0 },
      { ...booleanParam, name: 'explicit_false', value: false },
    ],
    userParams: {
      model_id: null,
      enabled: null,
      time: null,
      limit: 0,
      explicit_false: false,
    },
  }),
  { limit: 0, explicit_false: false },
  '请求必须省略 null 参数，同时保留 0 和 false',
);

const invalidFilterParam = {
  ...numberParam,
  filterType: 'filter' as const,
};
const validation = validateParams([invalidFilterParam]);
assert.equal(validation.isValid, false, '数字类型不能配置为画布筛选参数');
assert.deepEqual(validation.invalidFilterBindingIds, ['limit-param']);

const paramTableSource = readFileSync(
  fileURLToPath(
    new URL(
      '../src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx',
      import.meta.url,
    ),
  ),
  'utf8',
);
assert.match(
  paramTableSource,
  /type === ["']number["'][\s\S]{0,120}val === ["']["'] \? null : Number\(val\)/,
  '数据源编辑器必须保留数字输入的清空状态',
);
assert.match(
  paramTableSource,
  /isBindableDataSourceParamType\(\s*record\.type,?\s*\)[\s\S]{0,220}\? filterTypeOptions/,
  '筛选类型选项必须按参数类型限制',
);

const paramsConfigSource = readFileSync(
  fileURLToPath(
    new URL('../src/app/ops-analysis/components/paramsConfig.tsx', import.meta.url),
  ),
  'utf8',
);
assert.match(
  paramsConfigSource,
  /clearable=\{!disabled\}/,
  'timeRange 参数必须允许非只读控件显式清空',
);
assert.match(
  paramsConfigSource,
  /disabled=\{isDisabled\}\s+allowClear=\{!isDisabled\}\s+options=\{options\}/,
  '非固定的静态选项参数必须允许清空',
);
assert.match(
  paramsConfigSource,
  /originValue == null[\s\S]{0,100}onChange\?\.\(null\)/,
  'timeRange 清空必须向表单传递 null',
);
assert.match(
  paramsConfigSource,
  /case ['"]boolean['"]:\s*return \([\s\S]{0,260}<NullableBooleanSelect[\s\S]{0,120}disabled=\{isDisabled\}/,
  'boolean 参数必须使用能够区分 null 与 false 的可清空控件',
);

console.log('ops analysis parameter contract tests passed');
