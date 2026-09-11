import React, { useEffect, useRef, useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { Form, Input, Radio } from 'antd';
import { IntlProvider } from 'react-intl';
import CommonContextProvider from '@/app/alarm/context/common';
import MatchRule from '@/app/alarm/(pages)/settings/components/matchRule';
import zh from '@/app/alarm/locales/zh.json';
import commonZh from '@/locales/zh.json';
import { useThemeMode } from '@/theme';

const flatten = (source: Record<string, unknown>, prefix = ''): Record<string, string> =>
  Object.fromEntries(Object.entries(source).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === 'string' ? [[path, value]] : Object.entries(flatten(value as Record<string, unknown>, path));
  }));

const Editor = (args: React.ComponentProps<typeof MatchRule>) => {
  const [value, setValue] = useState(args.value);
  const { mode, setMode } = useThemeMode();
  const originalMode = useRef(mode);
  useEffect(() => {
    setMode('light');
    return () => setMode(originalMode.current);
  }, [setMode]);
  return (
    <div className="w-[740px] max-w-full bg-[var(--color-bg-1)] p-6">
      <h3 className="mb-6 text-base font-semibold">{{correlation:'相关性规则',assignment:'告警分派',shield:'屏蔽策略',enrichment:'告警丰富',action:'告警处理'}[args.scope || 'assignment']}</h3>
      <Radio.Group className="mb-4" aria-label="预览主题" value={mode} onChange={event => setMode(event.target.value)}
        options={[{ label: '浅色', value: 'light' }, { label: '深色', value: 'dark' }]} />
      <Form layout="vertical">
        <Form.Item label="策略名称" required><Input placeholder="请输入策略名称" /></Form.Item>
        <Form.Item label="匹配规则" required><Radio.Group value="filter" options={[{ label: '全部', value: 'all' }, { label: '筛选', value: 'filter' }]} /></Form.Item>
        <Form.Item><MatchRule {...args} value={value} onChange={setValue} /></Form.Item>
      </Form>
    </div>
  );
};

const meta = {
  title: 'Business/Alarm/RuleEditor',
  component: MatchRule,
  decorators: [(Story) => (
    <IntlProvider locale="zh" messages={{ ...flatten(commonZh), ...flatten(zh) }}>
      <CommonContextProvider><Story /></CommonContextProvider>
    </IntlProvider>
  )],
  render: (args) => <Editor {...args} />,
} satisfies Meta<typeof MatchRule>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Assignment: Story = {
  args: { monitorSourceField: 'push_source_ids', value: [[{ key: 'push_source_ids', operator: 'none_of', value: ['test'] }]] },
};
export const Shield: Story = {
  args: { monitorSourceField: 'push_source_id', value: [[{ key: 'push_source_id', operator: 'none_of', value: ['k8s-prod'] }]] },
};
export const MultipleGroups: Story = {
  args: { monitorSourceField: 'push_source_ids', value: [
    [{ key: 'push_source_ids', operator: 'any_of', value: ['k8s-prod'] }, { key: 'title', operator: 'contains', value: 'CPU' }],
    [{ key: 'push_source_ids', operator: 'any_of', value: ['prometheus-prod'] }],
  ] },
};

export const MultiAssignment: Story = {
  args:{scope:'assignment',levelType:'alert',value:[[
    {key:'push_source_ids',operator:'all_of',value:['a','b']},
    {key:'source_names',operator:'all_of',value:['平台A','平台B']},
    {key:'level',operator:'any_of',value:['1','2']},
  ]]},
};
export const MultiShield: Story = {
  args:{scope:'shield',value:[[{key:'push_source_id',operator:'any_of',value:['a']}]]},
};
export const MultiCorrelation: Story = {
  args:{scope:'correlation',value:[[{key:'item',operator:'re',value:'^(cpu|memory)$'}]]},
};
export const MultiEnrichment: Story = {
  args:{scope:'enrichment',value:[[{key:'description',operator:'contains',value:'CPU busy'}]]},
};
export const MultiAction: Story = {
  args:{scope:'action',levelType:'alert',value:[[{key:'push_source_ids',operator:'none_of',value:['test-a','test-b']}]]},
};
