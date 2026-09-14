import React, { useEffect, useRef } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { IntlProvider } from 'react-intl';
import MonitorSourceList from '@/app/alarm/components/monitor-source-list';
import zh from '@/app/alarm/locales/zh.json';
import { useThemeMode } from '@/theme';

const DarkPreview = ({ children }: { children: React.ReactNode }) => {
  const { mode, setMode } = useThemeMode();
  const initialMode = useRef(mode);
  useEffect(() => {
    setMode('dark');
    return () => setMode(initialMode.current);
  }, [setMode]);
  return <>{children}</>;
};

const messages = Object.fromEntries(
  Object.entries(zh.alarmCommon).filter((entry): entry is [string, string] => typeof entry[1] === 'string')
    .map(([key, value]) => [`alarmCommon.${key}`, value]),
);

const meta = {
  title: 'Business/Alarm/MonitorSources',
  component: MonitorSourceList,
  decorators: [(Story) => (
    <IntlProvider locale="zh" messages={messages}>
      <div className="max-w-xl p-6">
        <div className="mb-2 text-sm">监控源</div>
        <Story />
      </div>
    </IntlProvider>
  )],
} satisfies Meta<typeof MonitorSourceList>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Multiple: Story = {
  args: { sources: ['001', '1', 'k8s-prod', 'prometheus-prod-cluster-001', 'zabbix-test'] },
};

export const LongValue: Story = {
  args: { sources: ['monitoring-source-production-cluster-' + '0123456789'.repeat(6)] },
};

export const Empty: Story = { args: { sources: [] } };

export const Dark: Story = {
  args: Multiple.args,
  decorators: [(Story) => (
    <DarkPreview><Story /></DarkPreview>
  )],
};
