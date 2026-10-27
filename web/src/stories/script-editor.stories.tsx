import type { Meta, StoryObj } from '@storybook/nextjs';
import ScriptEditor from '@/components/script-editor';

const sampleValue = {
  shell: '#!/bin/bash\necho "hello from shell"\n',
  bat: '@echo off\necho hello from bat\r\n',
  python: 'print("hello from python")\n',
  powershell: 'Write-Host "hello from powershell"\n',
};

const jobVariables = [
  {
    key: 'BK_JOB_USER',
    description: '执行用户',
    token: { shell: '$BK_JOB_USER', powershell: '$BK_JOB_USER', python: 'BK_JOB_USER', bat: '%BK_JOB_USER%' },
  },
  {
    key: 'BK_JOB_USER_NAME',
    description: '用户中文名',
    token: { shell: '$BK_JOB_USER_NAME', powershell: '$BK_JOB_USER_NAME', python: 'BK_JOB_USER_NAME', bat: '%BK_JOB_USER_NAME%' },
  },
  {
    key: 'BK_JOB_ID',
    description: '作业 ID',
    token: { shell: '$BK_JOB_ID', powershell: '$BK_JOB_ID', python: 'BK_JOB_ID', bat: '%BK_JOB_ID%' },
  },
];

const meta = {
  title: 'Components/ScriptEditor',
  component: ScriptEditor,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 960, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof ScriptEditor>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    value: sampleValue,
    activeLang: 'shell',
    onChange: () => undefined,
  },
};

export const JobVariables: Story = {
  args: {
    value: sampleValue,
    activeLang: 'shell',
    onChange: () => undefined,
    variablePanel: {
      visible: true,
      followFullscreen: false,
      defaultExpanded: false,
      variables: jobVariables,
    },
  },
};
