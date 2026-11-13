import React, { useMemo } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { Form } from 'antd';
import { IntlProvider } from 'react-intl';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { getDataSourceFormParamInitialValue } from '@/app/ops-analysis/utils/dataSourceFormParams';
import zhOps from '@/app/ops-analysis/locales/zh.json';

type LocaleJson = Record<string, unknown>;

const flatten = (obj: LocaleJson, prefix = '', out: Record<string, string> = {}) => {
  Object.keys(obj).forEach((key) => {
    const value = obj[key];
    const messageKey = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      flatten(value as LocaleJson, messageKey, out);
    } else {
      out[messageKey] = String(value);
    }
  });
  return out;
};

const messages = flatten(zhOps as LocaleJson);

const params: ParamItem[] = [
  {
    name: 'analysis_mode',
    alias_name: '分析方式',
    type: 'string',
    filterType: 'params',
    value: 'detail',
    required: true,
    inputConfig: {
      control: 'select',
      optionsSource: {
        type: 'static',
        staticItems: [
          { label: '明细', value: 'detail', charts: ['table'], result: { structure: 'table' } },
          { label: '计数', value: 'count', charts: ['single'], result: { structure: 'value' } },
        ],
      },
    },
  },
  {
    name: 'result_filter',
    alias_name: '实例数筛选',
    type: 'conditionFilter',
    filterType: 'params',
    value: { logic: 'OR', items: [{ field: 'instance_count', op: 'gt', value: 3 }] },
    inputConfig: {
      control: 'conditionFilter',
      fields: {
        kind: 'static',
        items: [{ value: 'instance_count', label: '实例数', valueType: 'number', options: [] }],
      },
    },
    visible_modes: ['detail', 'count', 'distribution'],
  },
  {
    name: 'filters',
    alias_name: '属性过滤',
    type: 'conditionFilter',
    filterType: 'params',
    value: { logic: 'AND', items: [{ field: 'os', op: 'eq', value: 'linux' }] },
    inputConfig: {
      control: 'conditionFilter',
      fields: {
        kind: 'static',
        items: [
          { value: 'name', label: '名称', valueType: 'string' },
          {
            value: 'os',
            label: '系统',
            valueType: 'enum',
            options: [{ label: 'Linux', value: 'linux' }, { label: 'Windows', value: 'windows' }],
          },
        ],
      },
    },
  },
  {
    name: 'order',
    alias_name: '排序',
    type: 'order',
    filterType: 'params',
    value: '-instance_count',
    visible_modes: ['detail', 'distribution'],
    inputConfig: {
      control: 'order',
      fields: [
        { value: 'instance_count', label: '实例数', modes: ['detail'] },
        { value: 'model_name', label: '模型名称', modes: ['detail'] },
      ],
    },
  },
  {
    name: 'page',
    alias_name: '页码',
    type: 'number',
    filterType: 'params',
    value: 1,
    visible_modes: ['detail'],
  },
  {
    name: 'page_size',
    alias_name: '每页条数',
    type: 'number',
    filterType: 'params',
    value: 20,
    visible_modes: ['detail'],
  },
];

const source = {
  id: 54,
  name: 'CMDB 模型通用查询',
  params,
} as DatasourceItem;

const NarrowDrawerView = () => {
  const [form] = Form.useForm();
  const initialParams = useMemo(() => {
    const values: Record<string, unknown> = {};
    params.forEach((param) => {
      values[param.name] = getDataSourceFormParamInitialValue(param);
    });
    return values;
  }, []);
  return (
    <IntlProvider locale="zh" messages={messages}>
      <div data-testid="narrow-config-drawer" style={{ width: 320 }} className="bg-[var(--color-bg)] p-3">
        <Form
          form={form}
          layout="vertical"
          initialValues={{ chartType: 'table', params: initialParams }}
        >
          <DataSourceParamsConfig selectedDataSource={source} />
        </Form>
      </div>
    </IntlProvider>
  );
};

const meta: Meta<typeof NarrowDrawerView> = {
  title: 'Ops Analysis/Generic Query Filters',
  component: NarrowDrawerView,
};

export default meta;

type Story = StoryObj<typeof NarrowDrawerView>;

/** 320px 宽的组件配置区，用来核对条件行和排序没有被挤掉。 */
export const NarrowDrawer: Story = {};
