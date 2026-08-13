'use client';

import {
  CloudUploadOutlined,
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
    <div className="h-full overflow-auto p-4 lg:p-5">
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
