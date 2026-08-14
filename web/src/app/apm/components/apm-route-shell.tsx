'use client';

import { Empty } from 'antd';
import type { ReactNode } from 'react';
import { useTranslation } from '@/utils/i18n';

interface ApmRouteShellProps {
  title: string;
  /** 保留为路由元数据，页面不再重复渲染说明卡。 */
  description: string;
  /** 保留为路由元数据，页面不再用装饰图标表达依赖类型。 */
  dependency?: 'metadata' | 'telemetry' | 'control';
  children?: ReactNode;
}

export default function ApmRouteShell({
  title,
  children,
}: ApmRouteShellProps) {
  const { t } = useTranslation();
  return (
    <div className="h-full overflow-auto px-4 pb-4 lg:px-5 lg:pb-5">
      <div className="mx-auto w-full min-w-0 max-w-[1920px]">
        <h1 className="sr-only">{title}</h1>
        <div className="min-w-0">
          {children ?? (
            <ApmSurface className="py-12">
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('apm.common.routeShellEmpty', '路由与权限壳已就绪，业务数据将在后续切片接入。')}
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
