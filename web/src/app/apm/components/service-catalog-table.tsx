'use client';

import Link from 'next/link';
import { BellOutlined } from '@ant-design/icons';
import { Button, Grid, Space, Tag, Typography, type TableColumnsType, type TableProps } from 'antd';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import {
  formatDateTime,
  formatErrorRate,
  formatLatency,
  formatPercentage,
  formatThroughput,
  isErrorRateDanger,
} from '@/app/apm/components/metric-format';
import MetricValue from '@/app/apm/components/metric-value';
import MiniTrend from '@/app/apm/components/mini-trend';
import {
  alertKey,
  alertStatusFromLevel,
  alertStatusMeta,
  metricKey,
  type ServiceEnvironmentRow,
  type TimeWindow,
} from '@/app/apm/components/service-catalog-model';
import ServiceLanguage from '@/app/apm/components/service-language';
import type { ApmServiceRed, ApmSlo } from '@/app/apm/types';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import Permission from '@/components/permission';
import { useTranslation } from '@/utils/i18n';

export default function ServiceCatalogTable({
  rows,
  redMetrics,
  metricFailureKeys,
  alertCounts,
  sloByServiceEnv,
  timeWindow,
  groupNames,
  selectedApplicationName,
  onAdjustOrganization,
  onArchive,
  onRetryMetrics,
  rowSelection,
}: {
  rows: ServiceEnvironmentRow[];
  redMetrics: Record<string, ApmServiceRed>;
  metricFailureKeys: string[];
  alertCounts: Map<string, { count: number; level: number }>;
  sloByServiceEnv: Map<string, ApmSlo>;
  timeWindow: TimeWindow;
  groupNames: Map<number, string>;
  selectedApplicationName?: string;
  onAdjustOrganization: (serviceId: string) => void;
  onArchive: (serviceId: string) => void;
  onRetryMetrics?: () => void;
  rowSelection?: TableProps<ServiceEnvironmentRow>['rowSelection'];
}) {
  const { t } = useTranslation();
  const screens = Grid.useBreakpoint();

  const columns: TableColumnsType<ServiceEnvironmentRow> = [
    {
      title: (
        <Space size={6}>
          <span>{t('apm.common.service', '服务')}</span>
          {selectedApplicationName ? (
            <Tag bordered={false} color="blue" className="!m-0 !text-xs">
              {selectedApplicationName}
            </Tag>
          ) : null}
        </Space>
      ),
      key: 'service',
      render: (_, item) => {
        const silent = item.status === 'silent';
        const href = item.environment
          ? `/apm/services/${item.serviceId}?environment=${encodeURIComponent(item.environment)}&window=${timeWindow}`
          : undefined;
        return (
          <Space size={8} align="center" className={silent ? 'opacity-60' : undefined}>
            <ServiceLanguage language={item.language} />
            {href ? (
              <Link
                href={href}
                className="font-medium text-[var(--color-primary)] hover:underline"
              >
                {item.serviceName}
              </Link>
            ) : (
              <Typography.Text strong className="!text-sm">{item.serviceName}</Typography.Text>
            )}
            {silent ? <Tag bordered={false} className="!m-0 !text-xs text-[var(--color-text-3)]">{t('apm.status.silent', '静默')}</Tag> : null}
          </Space>
        );
      },
    },
    {
      title: t('apm.common.status', '状态'),
      key: 'status',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      align: 'center',
      render: (_, item) => {
        const status = alertStatusFromLevel(alertCounts.get(alertKey(item.serviceName, item.environment))?.level);
        const presentation = alertStatusMeta[status];
        const label = t(presentation.id, presentation.fallback);
        return (
          <Tag
            bordered={false}
            color={presentation.color}
            aria-label={t('apm.application.highestAlert', '最高活跃告警：{label}', { label })}
            className="!m-0"
          >
            {label}
          </Tag>
        );
      },
    },
    {
      title: t('apm.services.activeAlerts', '活跃告警'),
      key: 'alerts',
      width: APM_TABLE_COLUMN_WIDTHS.compact,
      align: 'center',
      responsive: ['md'],
      render: (_, item) => {
        const alert = alertCounts.get(alertKey(item.serviceName, item.environment));
        const count = alert?.count ?? 0;
        const dangerous = count > 0 && (alert?.level ?? 5) <= 2;
        const eventsHref = `/apm/events/alerts?service=${encodeURIComponent(item.serviceName)}${
          item.environment ? `&environment=${encodeURIComponent(item.environment)}` : ''
        }`;
        return (
          <Link
            href={eventsHref}
            aria-label={t('apm.services.alertsAria', '{name} 有 {count} 个活跃告警，查看告警', { name: item.serviceName, count })}
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs no-underline transition-colors duration-150 ${
              dangerous
                ? 'border-[var(--color-fail)] bg-[color-mix(in_srgb,var(--color-fail)_10%,var(--color-bg))] font-semibold text-[var(--color-fail)]'
                : 'border-[var(--color-border)] bg-[var(--color-fill-1)] text-[var(--color-text-3)] hover:border-[var(--color-primary)]'
            }`}
            onClick={(event) => event.stopPropagation()}
          >
            <BellOutlined className="text-[10px]" aria-hidden="true" />
            <span className="tabular-nums">{count}</span>
            <span className="sr-only">{t('apm.services.activeAlertsUnit', '个活跃告警')}</span>
          </Link>
        );
      },
    },
    {
      title: t('apm.common.throughputPerSec', '吞吐量(/s)'),
      key: 'throughput',
      width: APM_TABLE_COLUMN_WIDTHS.metricWide,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['md'],
      render: (_, item) => {
        const metric = redMetrics[metricKey(item.serviceId, item.environment)];
        const unavailable = metricFailureKeys.includes(metricKey(item.serviceId, item.environment));
        return (
          <MetricValue
            text={formatThroughput(metric?.request_rate ?? null, unavailable, t)}
            unavailable={unavailable}
            muted={item.status === 'silent'}
            onRetry={unavailable ? onRetryMetrics : undefined}
          />
        );
      },
    },
    {
      title: t('apm.common.errorRate', '错误率'),
      key: 'errorRate',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['md'],
      render: (_, item) => {
        const metric = redMetrics[metricKey(item.serviceId, item.environment)];
        const unavailable = metricFailureKeys.includes(metricKey(item.serviceId, item.environment));
        return (
          <MetricValue
            text={formatErrorRate(metric?.error_rate ?? null, unavailable, t)}
            unavailable={unavailable}
            danger={isErrorRateDanger(metric?.error_rate ?? null)}
            onRetry={unavailable ? onRetryMetrics : undefined}
          />
        );
      },
    },
    {
      title: t('apm.common.p99', 'P99'),
      key: 'p99',
      width: APM_TABLE_COLUMN_WIDTHS.compact,
      align: 'right',
      className: 'tabular-nums',
      responsive: ['lg'],
      render: (_, item) => {
        const metric = redMetrics[metricKey(item.serviceId, item.environment)];
        const unavailable = metricFailureKeys.includes(metricKey(item.serviceId, item.environment));
        return (
          <MetricValue
            text={formatLatency(metric?.p99_ms ?? null, unavailable, t)}
            unavailable={unavailable}
            onRetry={unavailable ? onRetryMetrics : undefined}
          />
        );
      },
    },
    {
      title: t('apm.services.trend', '趋势'),
      key: 'trend',
      width: APM_TABLE_COLUMN_WIDTHS.trend,
      responsive: ['xl'],
      render: (_, item) => {
        const metric = redMetrics[metricKey(item.serviceId, item.environment)];
        return (
          <MiniTrend
            points={metric?.timeseries}
            status={item.status}
            errorRate={metric?.error_rate ?? null}
          />
        );
      },
    },
    {
      title: t('apm.common.environment', '环境'),
      dataIndex: 'environment',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      responsive: ['lg'],
      render: (value) => <Tag bordered={false}>{value || t('apm.common.unset', '未设置')}</Tag>,
    },
    {
      title: t('apm.slo.title', 'SLO'),
      key: 'slo',
      width: APM_TABLE_COLUMN_WIDTHS.metric,
      responsive: ['xl'],
      render: (_, item) => {
        const slo = sloByServiceEnv.get(metricKey(item.serviceId, item.environment));
        if (!slo) return <Typography.Text type="secondary">—</Typography.Text>;
        const met = slo.budget_remaining !== null && slo.budget_remaining > 0
          && slo.current_rate !== null
          && Number(slo.current_rate) >= Number(slo.objective);
        return (
          <Tag
            bordered={false}
            className={`!m-0 !text-xs ${
              met
                ? '!bg-[color-mix(in_srgb,var(--color-success)_12%,var(--color-bg))] !text-[var(--color-success)]'
                : '!bg-[color-mix(in_srgb,var(--color-fail)_12%,var(--color-bg))] !text-[var(--color-fail)]'
            }`}
          >
            {met ? t('apm.services.met', '达标') : t('apm.services.unmet', '未达标')}
            {slo.current_rate !== null ? ` ${formatPercentage(slo.current_rate, 1)}` : ''}
          </Tag>
        );
      },
    },
    {
      title: t('apm.common.lastSeen', '最近活跃'),
      dataIndex: 'last_seen_at',
      width: APM_TABLE_COLUMN_WIDTHS.timestamp,
      responsive: ['xl'],
      render: (value) => (
        <time
          className="whitespace-nowrap tabular-nums text-[var(--color-text-1)]"
          dateTime={value}
          title={formatDateTime(value)}
        >
          {formatDateTime(value, false)}
        </time>
      ),
    },
    {
      title: t('apm.common.organization', '组织'),
      dataIndex: 'serviceOrganizationIds',
      width: APM_TABLE_COLUMN_WIDTHS.organization,
      responsive: ['xxl'],
      render: (value: number[]) => value.length
        ? value.map((id) => (
          <Tag bordered={false} key={id}>{groupNames.get(id) ?? `#${id}`}</Tag>
        ))
        : <Typography.Text type="secondary">—</Typography.Text>,
    },
    {
      title: t('apm.common.operation', '操作'),
      key: 'action',
      width: screens.sm ? APM_TABLE_COLUMN_WIDTHS.actionPair : APM_TABLE_COLUMN_WIDTHS.singleAction,
      align: 'right',
      fixed: 'right',
      render: (_, item) => (
        <Permission requiredPermissions={['Operate']} permissionPath="/apm/services">
          {screens.sm ? (
            <Space className="whitespace-nowrap" size={8}>
              <Button
                className="!px-0"
                size="small"
                type="link"
                onClick={(event) => {
                  event.stopPropagation();
                  onAdjustOrganization(item.serviceId);
                }}
              >
                {t('apm.services.adjustOrgAction', '调整组织')}
              </Button>
              <Button
                className="!px-0"
                danger
                size="small"
                type="link"
                onClick={(event) => {
                  event.stopPropagation();
                  onArchive(item.serviceId);
                }}
              >
                {t('apm.services.archive', '归档')}
              </Button>
            </Space>
          ) : (
            <MoreActionsDropdown
              ariaLabel={t('apm.serviceDetail.moreActions', '更多操作')}
              buttonType="link"
              items={[
                {
                  key: 'organization',
                  label: t('apm.services.adjustOrgAction', '调整组织'),
                  onClick: () => onAdjustOrganization(item.serviceId),
                },
                {
                  key: 'archive',
                  danger: true,
                  label: t('apm.services.archive', '归档'),
                  onClick: () => onArchive(item.serviceId),
                },
              ]}
              stopPropagation
            />
          )}
        </Permission>
      ),
    },
  ];

  return (
    <ApmDataTable
      columns={columns}
      dataSource={rows}
      headerAlignment="column"
      rowKey="key"
      rowSelection={rowSelection}
      pagination={{
        defaultPageSize: 20,
        pageSizeOptions: [10, 20, 50, 100],
        showSizeChanger: true,
        showTotal: (total) => t('apm.common.paginationTotal', '共 {total} 条', { total }),
      }}
    />
  );
}
