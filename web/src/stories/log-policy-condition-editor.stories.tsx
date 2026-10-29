import React, { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { IntlProvider } from 'react-intl';
import ConditionSelector from '@/app/log/(pages)/event/strategy/detail/conditionSelector';
import zh from '@/app/log/locales/zh.json';
import { FilterItem } from '@/app/log/types/integration';

/**
 * 日志聚合策略的告警条件编辑器。一条条件一张卡：统计、比较、触发。
 */

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

const FIELDS = ['level', 'duration', '_msg'];

const freshCondition = (): FilterItem[] => [
  { func: 'count', field: '_msg', op: '>', value: '' },
];

const wideConditions = (): FilterItem[] => [
  { func: 'count', field: 'level', op: '>', value: '100', compare: { kind: 'absolute' } },
  {
    func: 'avg',
    field: 'duration',
    op: '>',
    value: '20',
    compare: { kind: 'percent', to: 'offset_hours', offset: 24 },
  },
  {
    func: 'quantile',
    field: 'duration',
    op: '>',
    value: '2000',
    params: { quantile: 0.95 },
  },
  {
    func: 'ratio',
    field: '_msg',
    op: '>',
    value: '5',
    params: { filter: 'status:500' },
  },
  { func: 'count_rate', field: '_msg', op: '>', value: '0.5' },
];

function EditorDemo({
  initialTerm = 'or',
  initialData,
  className,
}: {
  initialTerm?: string;
  initialData: FilterItem[];
  className?: string;
}) {
  const [term, setTerm] = useState(initialTerm);
  const [data, setData] = useState(initialData);
  return (
    <div className={className}>
      <ConditionSelector
        term={term}
        onTermChange={setTerm}
        data={data}
        fields={FIELDS}
        onChange={setData}
      />
    </div>
  );
}

const meta: Meta<typeof ConditionSelector> = {
  title: 'Business/Log/PolicyConditionEditor',
  component: ConditionSelector,
  decorators: [
    (Story) => (
      <IntlProvider locale="zh" messages={flatten(zh as LocaleJson)}>
        <div className="bg-[var(--color-bg-2)] p-6">
          <Story />
        </div>
      </IntlProvider>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof ConditionSelector>;

/** 新建态：一条计数条件，阈值为空。 */
export const Default: Story = {
  render: () => <EditorDemo className="w-[820px]" initialData={freshCondition()} />,
};

/** 五条条件，最宽的一条在 820px 内容器内折行。 */
export const MultipleConditions: Story = {
  render: () => <EditorDemo className="w-[820px]" initialData={wideConditions()} />,
};

/** 同上数据放进 560px 窄容器。 */
export const NarrowContainer: Story = {
  render: () => <EditorDemo className="max-w-[560px]" initialData={wideConditions()} />,
};

/** 只有一条时不出现删除按钮。 */
export const SingleWithoutDelete: Story = {
  render: () => <EditorDemo className="w-[820px]" initialData={freshCondition()} />,
};

/** 大于运算符下警告、错误、严重三档并排。 */
export const ThresholdLadder: Story = {
  render: () => (
    <EditorDemo
      className="w-[820px]"
      initialData={[
        {
          func: 'count',
          field: '_msg',
          op: '>',
          value: '10',
          thresholds: [
            { level: 'warning', value: '10' },
            { level: 'error', value: '50' },
            { level: 'critical', value: '200' },
          ],
        },
      ]}
    />
  ),
};

/** 等于也按警告、错误、严重三档填写，只保留有值的那一档。 */
export const DegradedEquality: Story = {
  render: () => (
    <EditorDemo
      className="w-[820px]"
      initialData={[{ func: 'count', field: 'level', op: '=', value: 'error' }]}
    />
  ),
};
