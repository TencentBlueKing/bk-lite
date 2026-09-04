'use client';

import type { ReactNode } from 'react';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';

interface ApmRouteShellProps {
  title: string;
  /** 保留为路由元数据，页面不再重复渲染说明卡。 */
  description: string;
  /** 保留为路由元数据，页面不再用装饰图标表达依赖类型。 */
  dependency?: 'metadata' | 'telemetry' | 'control';
  /**
   * 事件等工作区页面由自身管理分区留白时，可关闭 APM 默认的二次内边距；
   * `fill` 让子内容撑满一屏高度（子内容自行用 flex/min-h-0 分配），视口过矮时仍可滚动。
   */
  spacing?: 'default' | 'flush' | 'fill';
  children?: ReactNode;
}

export default function ApmRouteShell({
  title,
  spacing = 'default',
  children,
}: ApmRouteShellProps) {
  const { t } = useTranslation();
  // 水平 gutter 由全站 main.p-4 与二级 Segmented 共用，页面壳不再二次缩进。
  const shellClassName = spacing === 'flush'
    ? 'h-full min-h-0 overflow-auto'
    : 'h-full overflow-auto pb-4 lg:pb-5';
  const fill = spacing === 'fill';

  return (
    <div className={shellClassName}>
      <div className={`mx-auto w-full min-w-0 max-w-[1920px] ${fill ? 'flex h-full min-h-0 flex-col' : ''}`}>
        <h1 className="sr-only">{title}</h1>
        <div className={fill ? 'min-h-0 min-w-0 flex-1' : 'min-w-0'}>
          {children ?? (
            <ApmSurface className="py-12">
              <CompactEmptyState
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
  // 列表页默认 16px：Tab、搜索、按钮、分页都停在卡片内沿内侧，不贴圆角外框。
  const paddingClass = padding === 'none' ? '' : padding === 'compact' ? 'p-3' : 'p-4';
  return (
    <section
      className={`rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] ${paddingClass} ${className}`}
    >
      {children}
    </section>
  );
}
