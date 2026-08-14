'use client';

import { Button, Empty, Result, Skeleton } from 'antd';
import type { ReactNode } from 'react';
import { HandledRequestError } from '@/utils/request';
import { useTranslation } from '@/utils/i18n';

export type CatalogStateKind = 'loading' | 'empty' | 'forbidden' | 'degraded' | 'error';

export interface CatalogStateProps {
  kind: CatalogStateKind;
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  onRetry?: () => void;
  retryLoading?: boolean;
  compact?: boolean;
}

export function catalogErrorKind(error: unknown): Exclude<CatalogStateKind, 'loading' | 'empty'> {
  if (error instanceof HandledRequestError && error.status === 403) return 'forbidden';
  if (error instanceof HandledRequestError && error.status === 503) return 'degraded';
  return 'error';
}

export default function CatalogState({
  kind,
  title,
  description,
  action,
  onRetry,
  retryLoading = false,
  compact = false,
}: CatalogStateProps) {
  const { t } = useTranslation();
  const defaultTitle: Record<Exclude<CatalogStateKind, 'loading' | 'empty'>, string> = {
    forbidden: t('apm.catalog.forbiddenTitle', '无权访问当前组织的 APM 数据'),
    degraded: t('apm.catalog.degradedTitle', '遥测存储暂不可用'),
    error: t('apm.catalog.errorTitle', 'APM 数据加载失败'),
  };

  if (kind === 'loading') {
    return (
      <div
        className={compact ? 'min-h-24 p-4' : 'min-h-56 p-6'}
        aria-label={t('apm.catalog.loading', '加载 APM 数据')}
        aria-busy="true"
      >
        <Skeleton active paragraph={{ rows: compact ? 2 : 5 }} title={false} />
      </div>
    );
  }

  const recoveryAction = action ?? (onRetry && kind !== 'forbidden' ? (
    <Button loading={retryLoading} type="primary" onClick={onRetry}>
      {t('apm.common.reload', '重新加载')}
    </Button>
  ) : undefined);

  if (kind === 'empty') {
    return (
      <Empty
        className={compact ? 'my-5' : 'my-10'}
        description={description ?? t('apm.catalog.empty', '当前范围暂无 APM 数据')}
      >
        {recoveryAction}
      </Empty>
    );
  }
  if (kind === 'forbidden') {
    return (
      <Result
        className={compact ? '!py-6' : undefined}
        status="403"
        title={title ?? defaultTitle.forbidden}
        subTitle={description ?? t('apm.catalog.forbiddenDescription', '请联系组织管理员申请查看权限。')}
        extra={recoveryAction}
      />
    );
  }
  return (
    <div role="alert">
      <Result
        className={compact ? '!py-6' : undefined}
        status={kind === 'degraded' ? 'warning' : 'error'}
        title={title ?? defaultTitle[kind]}
        subTitle={description ?? (kind === 'degraded'
          ? t('apm.catalog.degradedDescription', '目录元数据仍然可用，请稍后重试遥测查询。')
          : t('apm.catalog.errorDescription', '请检查筛选条件或网络状态后重试。'))}
        extra={recoveryAction}
      />
    </div>
  );
}
