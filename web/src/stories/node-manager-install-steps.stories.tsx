import React from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { Progress, Steps, Tag } from 'antd';
import {
  CheckCircleFilled,
  ClockCircleFilled,
  CloseCircleFilled,
  LoadingOutlined,
} from '@ant-design/icons';

type StepStatus = 'success' | 'running' | 'waiting' | 'warning' | 'error';

interface OperationStep {
  title: string;
  status: StepStatus;
  time?: string;
  message: string;
  progress?: number;
  meta?: string;
  reason?: string;
  nextAction?: string;
  children?: OperationStep[];
}

const statusConfig: Record<StepStatus, {
  text: string;
  color: 'success' | 'processing' | 'warning' | 'error' | 'default';
  border: string;
  icon: React.ReactNode;
}> = {
  success: {
    text: '已完成',
    color: 'success',
    border: '#52c41a',
    icon: <CheckCircleFilled style={{ color: '#52c41a' }} />,
  },
  running: {
    text: '进行中',
    color: 'processing',
    border: '#1677ff',
    icon: <LoadingOutlined />,
  },
  waiting: {
    text: '未开始',
    color: 'default',
    border: '#d9d9d9',
    icon: <ClockCircleFilled style={{ color: '#8c8c8c' }} />,
  },
  warning: {
    text: '需关注',
    color: 'warning',
    border: '#faad14',
    icon: <ClockCircleFilled style={{ color: '#faad14' }} />,
  },
  error: {
    text: '失败',
    color: 'error',
    border: '#ff4d4f',
    icon: <CloseCircleFilled style={{ color: '#ff4d4f' }} />,
  },
};

const controllerRunningSteps: OperationStep[] = [
  {
    title: '检查登录凭据配置',
    status: 'success',
    time: '2026-06-26 10:18:12',
    message: 'Check credential configuration (password)',
  },
  {
    title: '下发安装命令',
    status: 'success',
    time: '2026-06-26 10:18:14',
    message: 'Installer command entered target node',
  },
  {
    title: '安装器执行',
    status: 'running',
    time: '2026-06-26 10:18:21',
    message: 'Controller package downloaded',
    progress: 50,
    meta: '安装器详细进度: 3/6',
    children: [
      { title: '获取安装会话', status: 'success', message: 'Installer session fetched' },
      { title: '准备目录', status: 'success', message: 'Directories prepared' },
      { title: '下载安装包', status: 'success', message: 'Controller package downloaded' },
      { title: '解压安装包', status: 'running', message: 'Extracting controller package' },
      { title: '写入运行配置', status: 'waiting', message: '--' },
      { title: '执行安装程序', status: 'waiting', message: '--' },
    ],
  },
  {
    title: '等待节点回连',
    status: 'waiting',
    message: '--',
  },
];

const controllerConnectivitySteps: OperationStep[] = [
  {
    title: '检查登录凭据配置',
    status: 'success',
    time: '2026-06-26 10:18:12',
    message: 'Check credential configuration (password)',
  },
  {
    title: '下发安装命令',
    status: 'success',
    time: '2026-06-26 10:18:14',
    message: 'Installer bootstrap completed',
  },
  {
    title: '安装器执行',
    status: 'success',
    time: '2026-06-26 10:18:39',
    message: 'Package installer finished',
    progress: 100,
    meta: '安装器详细进度: 6/6',
    children: [
      { title: '获取安装会话', status: 'success', message: 'Installer session fetched' },
      { title: '准备目录', status: 'success', message: 'Directories prepared' },
      { title: '下载安装包', status: 'success', message: 'Controller package downloaded' },
      { title: '解压安装包', status: 'success', message: 'Extracted 3144 files' },
      { title: '写入运行配置', status: 'success', message: 'Installer runtime configured' },
      { title: '执行安装程序', status: 'success', message: 'Package installer finished' },
    ],
  },
  {
    title: '等待节点回连',
    status: 'running',
    time: '2026-06-26 10:18:40',
    message: 'Wait for node connection',
    nextAction: '安装器已完成，正在等待节点侧 sidecar 回连。',
  },
];

const controllerFailedSteps: OperationStep[] = [
  {
    title: '检查登录凭据配置',
    status: 'success',
    time: '2026-06-26 10:18:12',
    message: 'Check credential configuration (password)',
  },
  {
    title: '下发安装命令',
    status: 'success',
    time: '2026-06-26 10:18:14',
    message: 'Installer command entered target node',
  },
  {
    title: '安装器执行',
    status: 'error',
    time: '2026-06-26 10:18:24',
    message: 'Download failed: object not found',
    meta: '安装器详细进度: 2/6',
    reason: 'Required installation package was not found in object storage',
    nextAction: '检查目标架构对应的控制器安装包是否已上传。',
    children: [
      { title: '获取安装会话', status: 'success', message: 'Installer session fetched' },
      { title: '准备目录', status: 'success', message: 'Directories prepared' },
      { title: '下载安装包', status: 'error', message: 'Download failed: object not found' },
      { title: '解压安装包', status: 'waiting', message: '--' },
      { title: '写入运行配置', status: 'waiting', message: '--' },
      { title: '执行安装程序', status: 'waiting', message: '--' },
    ],
  },
  {
    title: '等待节点回连',
    status: 'waiting',
    message: '--',
  },
];

const collectorSteps: OperationStep[] = [
  {
    title: '提交采集器动作',
    status: 'success',
    time: '2026-06-26 10:22:01',
    message: 'Submit collector restart action',
  },
  {
    title: '等待 Sidecar 确认',
    status: 'success',
    time: '2026-06-26 10:22:03',
    message: 'Sidecar acknowledged action',
  },
  {
    title: '执行采集器动作',
    status: 'running',
    time: '2026-06-26 10:22:05',
    message: 'Restarting Vector',
  },
  {
    title: '等待执行结果',
    status: 'waiting',
    message: '--',
  },
];

const samples = [
  { title: '控制器安装中', steps: controllerRunningSteps },
  { title: '等待节点回连', steps: controllerConnectivitySteps },
  { title: '控制器安装失败', steps: controllerFailedSteps },
  { title: '采集器普通操作', steps: collectorSteps },
];

const getStepStatus = (status: StepStatus): 'finish' | 'process' | 'wait' | 'error' => {
  if (status === 'error') return 'error';
  if (status === 'running') return 'process';
  if (status === 'waiting') return 'wait';
  return 'finish';
};

const CompactChildList = ({ steps }: { steps: OperationStep[] }) => (
  <div className="mt-[8px] space-y-[6px]">
    {steps.map((step) => {
      const config = statusConfig[step.status];
      return (
        <div
          key={step.title}
          className="flex items-start justify-between gap-[8px] rounded-[4px] bg-[var(--color-fill-2)] px-[10px] py-[7px]"
        >
          <div className="min-w-0">
            <div className="text-[12px] font-medium text-[var(--color-text-1)]">{step.title}</div>
            <div className="mt-[2px] break-words text-[12px] text-[var(--color-text-3)]">{step.message}</div>
          </div>
          <Tag className="m-0 shrink-0" color={config.color} bordered={false}>
            {config.text}
          </Tag>
        </div>
      );
    })}
  </div>
);

const StepBody = ({ step, tone }: { step: OperationStep; tone: 'card' | 'light' | 'current' }) => {
  const config = statusConfig[step.status];
  const isLight = tone === 'light';
  return (
    <div
      className={[
        'mt-[8px] rounded-[4px] p-[12px]',
        isLight ? 'border-0 bg-transparent pl-0' : 'border border-[var(--color-border-1)] bg-[var(--color-fill-1)]',
      ].join(' ')}
      style={isLight ? undefined : { borderLeftWidth: 4, borderLeftColor: config.border }}
    >
      <div className="text-[12px] text-[var(--color-text-3)]">
        [{step.time || '--'}]
      </div>
      <div className="mt-[4px] break-words text-[12px] text-[var(--color-text-1)]">
        {step.message}
      </div>
      {(step.meta || typeof step.progress === 'number') && (
        <div className="mt-[8px] flex flex-wrap items-center gap-[8px] text-[12px] text-[var(--color-text-2)]">
          {step.meta && <span>{step.meta}</span>}
          {typeof step.progress === 'number' && (
            <div className="min-w-[160px] flex-1">
              <Progress percent={step.progress} size="small" showInfo={false} />
            </div>
          )}
        </div>
      )}
      {step.reason && (
        <div className="mt-[8px] text-[12px] text-[var(--color-error)]">
          失败原因: {step.reason}
        </div>
      )}
      {step.nextAction && (
        <div className="mt-[4px] text-[12px] text-[var(--color-text-2)]">
          下一步建议: {step.nextAction}
        </div>
      )}
      {step.children?.length ? (
        tone === 'current' ? (
          <div className="mt-[10px] border-t border-[var(--color-border-1)] pt-[10px]">
            <CompactChildList steps={step.children} />
          </div>
        ) : (
          <CompactChildList steps={step.children} />
        )
      ) : null}
    </div>
  );
};

const OperationTimeline = ({
  title,
  description,
  steps,
  tone,
}: {
  title: string;
  description: string;
  steps: OperationStep[];
  tone: 'card' | 'light' | 'current';
}) => (
  <section className="rounded-[6px] border border-[var(--color-border-1)] bg-white p-[16px]">
    <div className="mb-[14px]">
      <div className="text-[14px] font-semibold text-[var(--color-text-1)]">{title}</div>
      <div className="mt-[4px] text-[12px] text-[var(--color-text-3)]">{description}</div>
    </div>
    <Steps
      direction="vertical"
      current={steps.filter((step) => step.status !== 'waiting').length}
      items={steps.map((step) => {
        const config = statusConfig[step.status];
        return {
          status: getStepStatus(step.status),
          icon: config.icon,
          title: (
            <div className="flex items-center justify-between gap-[12px]">
              <span className="text-[14px] font-medium text-[var(--color-text-1)]">{step.title}</span>
              <Tag className="m-0 shrink-0" color={config.color} bordered={false}>
                {config.text}
              </Tag>
            </div>
          ),
          description: <StepBody step={step} tone={tone} />,
        };
      })}
    />
  </section>
);

const ComparisonBoard = () => (
  <div className="min-h-screen bg-[var(--color-fill-2)] p-[24px]">
    <div className="mb-[20px]">
      <h1 className="m-0 text-[20px] font-semibold text-[var(--color-text-1)]">
        节点管理 / 安装步骤展示样式对比
      </h1>
      <p className="mt-[8px] max-w-[920px] text-[13px] leading-[22px] text-[var(--color-text-2)]">
        用同一组控制器安装和采集器操作数据对比三种视觉方向，重点看层级、密度、状态表达是否统一。
      </p>
    </div>
    <div className="grid grid-cols-3 gap-[16px]">
      <OperationTimeline
        title="A. 统一卡片式"
        description="推荐：所有操作共享同一套步骤卡片，安装器明细作为第 3 步的紧凑子列表。"
        steps={controllerRunningSteps}
        tone="card"
      />
      <OperationTimeline
        title="B. 轻量日志式"
        description="更像日志流，弱化卡片边框，视觉更轻，但失败/建议信息的承载感弱一些。"
        steps={controllerRunningSteps}
        tone="light"
      />
      <OperationTimeline
        title="C. 当前增强式"
        description="保留现状结构，只收紧内嵌明细，改动最小，但和普通操作仍略有差异。"
        steps={controllerRunningSteps}
        tone="current"
      />
    </div>
  </div>
);

const ScenarioBoard = () => (
  <div className="min-h-screen bg-[var(--color-fill-2)] p-[24px]">
    <div className="mb-[20px]">
      <h1 className="m-0 text-[20px] font-semibold text-[var(--color-text-1)]">
        推荐样式 A / 全状态预览
      </h1>
      <p className="mt-[8px] max-w-[920px] text-[13px] leading-[22px] text-[var(--color-text-2)]">
        将控制器安装和采集器操作放在同一视觉体系里，检查成功、进行中、失败和普通操作是否不突兀。
      </p>
    </div>
    <div className="grid grid-cols-2 gap-[16px]">
      {samples.map((sample) => (
        <OperationTimeline
          key={sample.title}
          title={sample.title}
          description="统一卡片式候选样式"
          steps={sample.steps}
          tone="card"
        />
      ))}
    </div>
  </div>
);

const meta: Meta = {
  title: 'Node Manager/Install Step Display',
  parameters: {
    layout: 'fullscreen',
  },
};

export default meta;

type Story = StoryObj;

export const StyleComparison: Story = {
  render: () => <ComparisonBoard />,
};

export const RecommendedAllStates: Story = {
  render: () => <ScenarioBoard />,
};
