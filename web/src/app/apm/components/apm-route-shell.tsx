'use client';

import {
  CloudUploadOutlined,
  InfoCircleOutlined,
  RadarChartOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Empty, Typography } from 'antd';
import type { ReactNode } from 'react';

const { Text, Title } = Typography;

interface ApmRouteShellProps {
  title: string;
  description: string;
  dependency?: 'metadata' | 'telemetry' | 'control';
  children?: ReactNode;
}

const dependencyCopy = {
  metadata: '接入与目录元数据可用；遥测数据将在数据面配置后出现。',
  telemetry: '遥测存储不可用时，本页会明确显示降级状态，不会将查询故障伪装成空数据。',
  control: '策略与告警事件由 APM 自己管理；外部通知渠道不可用不会影响事件查询。',
};

const dependencyIcon = {
  metadata: <CloudUploadOutlined aria-hidden="true" />,
  telemetry: <RadarChartOutlined aria-hidden="true" />,
  control: <SafetyCertificateOutlined aria-hidden="true" />,
};

export default function ApmRouteShell({
  title,
  description,
  dependency = 'metadata',
  children,
}: ApmRouteShellProps) {
  return (
    <div className="h-full overflow-auto bg-[var(--color-background-body)] p-4 lg:p-5">
      <div className="mx-auto flex w-full flex-col gap-4">
        <header className="flex flex-col gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3 md:flex-row md:items-center md:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[var(--color-primary-bg-active)] text-base text-[var(--color-primary)]">
              {dependencyIcon[dependency]}
            </span>
            <div className="min-w-0">
              <Title level={1} className="!mb-0 !text-base !font-semibold !leading-6">
                {title}
              </Title>
              <Text type="secondary" className="block text-xs leading-5">
                {description}
              </Text>
            </div>
          </div>
          <div className="flex max-w-xl items-start gap-2 text-xs leading-5 text-[var(--color-text-3)] md:justify-end md:text-right">
            <InfoCircleOutlined className="mt-1 shrink-0 text-[var(--color-primary)]" aria-hidden="true" />
            <span>{dependencyCopy[dependency]}</span>
          </div>
        </header>
        <div className="min-w-0">
          {children ?? (
            <ApmSurface className="py-12">
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="路由与权限壳已就绪，业务数据将在后续切片接入。"
              />
            </ApmSurface>
          )}
        </div>
      </div>
    </div>
  );
}

interface ApmSurfaceProps {
  children: ReactNode;
  className?: string;
  padding?: 'none' | 'compact' | 'normal';
}

export function ApmSurface({ children, className = '', padding = 'normal' }: ApmSurfaceProps) {
  const paddingClass = padding === 'none' ? '' : padding === 'compact' ? 'p-3' : 'p-4';
  return (
    <section
      className={`rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] ${paddingClass} ${className}`}
    >
      {children}
    </section>
  );
}
