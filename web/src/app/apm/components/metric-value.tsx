'use client';

import { ReloadOutlined } from '@ant-design/icons';
import { Button, Tooltip, Typography } from 'antd';
import { metricEmptyHint } from '@/app/apm/components/metric-format';

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
  const empty = text === '无数据' || text === '查询失败';
  const hint = empty ? metricEmptyHint(unavailable) : undefined;
  const sizeClass = size === 'lg'
    ? 'text-[22px] font-bold tabular-nums leading-none'
    : 'tabular-nums';
  const toneClass = unavailable
    ? 'text-[var(--theme-color-status-warning)]'
    : danger
      ? 'font-semibold text-[var(--color-fail)]'
      : muted || text === '无数据'
        ? 'text-[var(--color-text-3)]'
        : 'text-[var(--color-text-1)]';

  const content = unavailable && onRetry ? (
    <Button
      type="link"
      size="small"
      className={`!h-auto !p-0 ${size === 'lg' ? '!text-[22px] !font-bold' : '!text-xs'}`}
      icon={<ReloadOutlined aria-hidden="true" className="text-[11px]" />}
      onClick={(event) => {
        event.stopPropagation();
        onRetry();
      }}
      aria-label="重试 RED 指标"
    >
      查询失败
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
          <Typography.Text type="secondary" className="!text-[10px]">可重试</Typography.Text>
        ) : null}
      </span>
    </Tooltip>
  );
}
