'use client';

import { ReloadOutlined } from '@ant-design/icons';
import { Button, Tooltip, Typography } from 'antd';
import { metricEmptyHint } from '@/app/apm/components/metric-format';
import { useTranslation } from '@/utils/i18n';

interface MetricValueProps {
  text: string;
  unavailable?: boolean;
  danger?: boolean;
  muted?: boolean;
  /** 失败时可内联重试；不传则仅展示文案，依赖页级重试 */
  onRetry?: () => void;
  className?: string;
  size?: 'sm' | 'lg';
}

/** 统一 RED 指标展示：无数据 / 查询失败（可重试）/ 正常值 */
export default function MetricValue({
  text,
  unavailable = false,
  danger = false,
  muted = false,
  onRetry,
  className = '',
  size = 'sm',
}: MetricValueProps) {
  const { t } = useTranslation();
  const noData = t('apm.common.noData', '无数据');
  const queryFailed = t('apm.common.queryFailed', '查询失败');
  const empty = text === noData || text === queryFailed;
  const hint = empty ? metricEmptyHint(unavailable, t) : undefined;
  const sizeClass = size === 'lg'
    ? 'text-base font-semibold tabular-nums leading-6'
    : 'tabular-nums';
  const toneClass = unavailable
    ? 'text-[var(--theme-color-status-warning)]'
    : danger
      ? 'font-semibold text-[var(--color-fail)]'
      : muted || text === noData
        ? 'text-[var(--color-text-3)]'
        : 'text-[var(--color-text-1)]';

  const content = unavailable && onRetry ? (
    <Button
      type="link"
      size="small"
      className={`!h-auto !p-0 ${size === 'lg' ? '!text-base !font-semibold' : '!text-xs'}`}
      icon={<ReloadOutlined aria-hidden="true" className="text-xs" />}
      onClick={(event) => {
        event.stopPropagation();
        onRetry();
      }}
      aria-label={t('apm.common.retryRed', '重试 RED 指标')}
    >
      {queryFailed}
    </Button>
  ) : (
    <span className={`${sizeClass} ${toneClass} ${className}`}>{text}</span>
  );

  if (!hint) return content;

  return (
    <Tooltip title={hint}>
      <span className="inline-flex items-center gap-1">
        {content}
        {unavailable && !onRetry ? (
          <Typography.Text type="secondary" className="!text-[10px]">{t('apm.common.retryable', '可重试')}</Typography.Text>
        ) : null}
      </span>
    </Tooltip>
  );
}
