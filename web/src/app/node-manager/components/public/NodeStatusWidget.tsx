'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Badge, Button, Spin, Table, Tag, Tooltip } from 'antd';
import {
  DesktopOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import useNodeApi from '@/app/node-manager/api/useNodeApi';
import { listNodeHostedCollectors } from '@/app/node-manager/utils/collectorConfig';
import {
  collectorStatusI18nKey,
  collectorStatusTagColor,
  extractCollectorMessage,
  nodeOnlineI18nKey,
  parseComponentVersions,
  resolveSidecarStatusMessage,
  summarizeCollectorStatuses,
} from '@/app/node-manager/utils/nodeStatusDisplay';
import { publicWidgetErrorMessage } from './publicWidgetError';

export interface NodeStatusWidgetProps {
  nodeId: string;
}

interface NodeComponentVersion {
  component_type?: string;
  component_id?: string | number;
  version?: string;
  latest_version?: string;
  upgradeable?: boolean;
  message?: string;
  last_check_at?: string;
}

interface NodeCollectorItem {
  collector_id?: string;
  collector_name?: string;
  id?: string;
  name?: string;
  status?: string | number;
  message?: unknown;
  configuration_id?: string | number | Array<string | number> | null;
  [key: string]: unknown;
}

interface NodeStatusPayload {
  id?: string;
  name?: string;
  ip?: string;
  active?: boolean;
  operating_system?: string;
  cpu_architecture?: string;
  install_method?: string;
  cloud_region?: number;
  updated_at?: string;
  versions?: NodeComponentVersion[];
  status?: {
    status?: string | number;
    message?: string;
    collectors?: NodeCollectorItem[];
    collectors_install?: NodeCollectorItem[];
  };
}

const NodeStatusWidget = ({ nodeId }: NodeStatusWidgetProps) => {
  const { t } = useTranslation();
  const tRef = useRef(t);
  tRef.current = t;
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getNodeList } = useNodeApi();
  const getNodeListRef = useRef(getNodeList);
  getNodeListRef.current = getNodeList;
  const [node, setNode] = useState<NodeStatusPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const id = String(nodeId || '').trim();
    if (!id) {
      setLoading(false);
      setError(tRef.current('common.loadFailed'));
      setNode(null);
      return;
    }
    setLoading(true);
    setError(null);
    getNodeListRef
      .current({
        page: 1,
        page_size: 1,
        filters: {
          id: [{ lookup_expr: 'exact', value: id }],
        },
      })
      .then((data: { items?: NodeStatusPayload[] }) => {
        if (cancelled) return;
        const item = data?.items?.[0] || null;
        if (!item) {
          setError(tRef.current('node-manager.cloudregion.node.publicWidgetNotFound'));
          setNode(null);
          return;
        }
        setNode(item);
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(
            publicWidgetErrorMessage(
              requestError,
              tRef.current,
              'node-manager.cloudregion.node.publicWidgetNotFound',
            ),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [nodeId, reloadKey]);

  const { controller: controllerInfo, collectors: collectorVersions } = useMemo(
    () => parseComponentVersions(node?.versions as Array<Record<string, unknown>> | undefined),
    [node?.versions],
  );

  const hostedCollectors = useMemo(() => {
    if (!node) return [];
    const list = listNodeHostedCollectors(node as Parameters<typeof listNodeHostedCollectors>[0]);
    if (list.length > 0) return list as NodeCollectorItem[];
    return (node.status?.collectors || []) as NodeCollectorItem[];
  }, [node]);

  const collectorSummary = useMemo(
    () => summarizeCollectorStatuses(hostedCollectors),
    [hostedCollectors],
  );

  const collectorRows = useMemo(() => {
    return hostedCollectors.map((item, index) => {
      const id = String(item.collector_id || item.id || `collector-${index}`);
      const name = String(item.collector_name || item.name || id);
      const statusRaw = item.status;
      const statusStr = statusRaw == null || statusRaw === '' ? '' : String(statusRaw);
      const tagColor = collectorStatusTagColor(statusRaw);
      const i18nKey = collectorStatusI18nKey(statusRaw);
      const versionInfo = collectorVersions.get(id);
      const message = extractCollectorMessage(item.message);

      return {
        key: id,
        id,
        name,
        statusStr,
        tagColor,
        i18nKey,
        version: versionInfo?.version,
        latest_version: versionInfo?.latest_version,
        upgradeable: versionInfo?.upgradeable,
        message,
      };
    });
  }, [hostedCollectors, collectorVersions]);

  const columns = useMemo(() => [
    {
      title: t('node-manager.cloudregion.node.collector'),
      dataIndex: 'name',
      key: 'name',
      width: 180,
      render: (_: unknown, record: (typeof collectorRows)[number]) => (
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-medium text-[var(--color-text-1)]">
            {record.name}
          </span>
          {record.id && record.id !== record.name ? (
            <span className="truncate font-mono text-[11px] text-[var(--color-text-3)]">
              {record.id}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      title: t('node-manager.cloudregion.node.status'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (_: unknown, record: (typeof collectorRows)[number]) => (
        <Tag color={record.tagColor} className="m-0 text-xs">
          {t(record.i18nKey)}
        </Tag>
      ),
    },
    {
      title: t('node-manager.cloudregion.node.version'),
      dataIndex: 'version',
      key: 'version',
      width: 130,
      render: (_: unknown, record: (typeof collectorRows)[number]) => {
        if (!record.version) {
          return <span className="text-[var(--color-text-3)]">--</span>;
        }
        return (
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-xs text-[var(--color-text-2)]">
              {record.version}
            </span>
            {record.upgradeable ? (
              <Tooltip
                title={t('node-manager.cloudregion.node.collectorUpgradeable', '', {
                  version: record.latest_version || '--',
                })}
              >
                <Tag color="warning" className="m-0 px-1 text-[10px] leading-tight cursor-default">
                  {t('node-manager.cloudregion.node.upgradeableBadge')}
                </Tag>
              </Tooltip>
            ) : null}
          </div>
        );
      },
    },
    {
      title: t('node-manager.cloudregion.node.runningStatus'),
      dataIndex: 'message',
      key: 'message',
      render: (_: unknown, record: (typeof collectorRows)[number]) => {
        const isAbnormal =
          record.tagColor === 'error' || record.tagColor === 'warning';
        if (!record.message) {
          return <span className="text-[var(--color-text-3)]">--</span>;
        }
        return (
          <div
            className={`text-xs ${
              isAbnormal
                ? 'font-medium text-[var(--color-fail)]'
                : 'text-[var(--color-text-2)]'
            }`}
          >
            <EllipsisWithTooltip
              className="max-w-[340px] truncate"
              text={record.message}
            />
          </div>
        );
      },
    },
  ], [collectorRows, t]);

  if (loading && !node) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (error || !node) {
    return (
      <div className="flex min-h-[280px] flex-col items-center justify-center gap-3">
        <CompactEmptyState description={error || t('common.loadFailed')} />
        <Button onClick={() => setReloadKey((current) => current + 1)}>
          {t('common.retry')}
        </Button>
      </div>
    );
  }

  const onlineKey = nodeOnlineI18nKey(node.active);
  const sidecarMessage = resolveSidecarStatusMessage(
    node.active,
    node.status?.message,
  );
  const normalCollectorCount = hostedCollectors.filter(
    (item) => String(item.status) === '0',
  ).length;
  const abnormalCollectorCount = hostedCollectors.filter((item) => {
    const s = String(item.status ?? '');
    return s === '2' || s === '12';
  }).length;

  const collectorHealthText =
    hostedCollectors.length === 0
      ? '--'
      : abnormalCollectorCount > 0
        ? `${normalCollectorCount} / ${hostedCollectors.length} ${t('node-manager.cloudregion.node.normal')}`
        : `${normalCollectorCount} / ${hostedCollectors.length} ${t('node-manager.cloudregion.node.normal')}`;

  const osLabel =
    node.operating_system?.toLowerCase() === 'windows'
      ? 'Windows'
      : node.operating_system?.toLowerCase() === 'linux'
        ? 'Linux'
        : node.operating_system;

  return (
    <div className="flex min-w-0 flex-col gap-3 p-1">
      {/* 顶部节点概览 Header */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3.5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--color-fill-2)] text-[var(--color-text-2)]">
              <DesktopOutlined className="text-lg" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="max-w-[280px] truncate text-sm font-semibold text-[var(--color-text-1)]">
                  {node.name || node.ip || '--'}
                </span>
                {node.ip && node.name && node.name !== node.ip ? (
                  <Tag className="m-0 border-none bg-[var(--color-fill-1)] font-mono text-xs text-[var(--color-text-2)]">
                    {node.ip}
                  </Tag>
                ) : null}
                {osLabel ? (
                  <Tag className="m-0 text-xs text-[var(--color-text-2)]">
                    {osLabel}
                  </Tag>
                ) : null}
                {node.cpu_architecture ? (
                  <Tag className="m-0 text-xs text-[var(--color-text-3)]">
                    {node.cpu_architecture}
                  </Tag>
                ) : null}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-[var(--color-text-3)]">
                {node.install_method ? (
                  <span>
                    {t('node-manager.cloudregion.node.installMethod')}:{' '}
                    <span className="text-[var(--color-text-2)]">
                      {node.install_method === 'auto'
                        ? t('node-manager.cloudregion.node.auto')
                        : t('node-manager.cloudregion.node.manual')}
                    </span>
                  </span>
                ) : null}
                <span>
                  {t('node-manager.cloudregion.node.lastReportTime')}:{' '}
                  <span className="font-mono text-[var(--color-text-2)]">
                    {node.updated_at ? convertToLocalizedTime(node.updated_at) : '--'}
                  </span>
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Tooltip title={t('common.refresh')}>
              <Button
                size="small"
                icon={<ReloadOutlined spin={loading} />}
                onClick={() => setReloadKey((current) => current + 1)}
              />
            </Tooltip>
          </div>
        </div>
      </div>

      {/* 核心双指标卡片 (Sidecar 控制面 + 采集器数据面) */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {/* Sidecar 卡片 */}
        <div className="flex flex-col justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3.5 shadow-sm">
          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-3)]">
                {t('node-manager.cloudregion.node.sidecar')} (Sidecar)
              </span>
              {controllerInfo?.version ? (
                <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-3)]">
                  <span className="font-mono">v{controllerInfo.version}</span>
                  {controllerInfo.upgradeable ? (
                    <Tooltip
                      title={t('node-manager.cloudregion.node.controllerVersionTip')}
                    >
                      <Tag
                        color="warning"
                        className="m-0 cursor-default px-1 text-[10px] leading-tight"
                      >
                        {t('node-manager.cloudregion.node.controllerUpgradeable')}
                      </Tag>
                    </Tooltip>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              <Badge status={node.active ? 'success' : 'warning'} />
              <span className="text-base font-semibold text-[var(--color-text-1)]">
                {onlineKey ? t(onlineKey) : '--'}
              </span>
            </div>
          </div>
          {sidecarMessage ? (
            <div className="mt-2.5 rounded bg-[var(--color-fill-1)] px-2.5 py-1.5 text-xs text-[var(--color-text-2)]">
              {sidecarMessage}
            </div>
          ) : null}
        </div>

        {/* 托管采集器卡片 */}
        <div className="flex flex-col justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3.5 shadow-sm">
          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-3)]">
                {t('node-manager.cloudregion.node.hostedProgram')}
              </span>
              <span className="text-xs text-[var(--color-text-3)]">
                {t('node-manager.cloudregion.node.collectorTotal', '组件总数')}: {hostedCollectors.length}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold text-[var(--color-text-1)]">
                {collectorHealthText}
              </span>
            </div>
          </div>
          <div className="mt-2.5 flex min-h-[26px] flex-wrap items-center gap-1.5">
            {collectorSummary.length > 0 ? (
              collectorSummary.map((item) => (
                <Tag
                  key={item.status}
                  color={item.tagColor}
                  className="m-0 text-xs"
                >
                  {`${t(item.i18nKey)}: ${item.count}`}
                </Tag>
              ))
            ) : (
              <span className="text-xs text-[var(--color-text-3)]">--</span>
            )}
          </div>
        </div>
      </div>

      {/* 托管采集器明细表 */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3.5 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[var(--color-text-1)]">
              {t('node-manager.cloudregion.node.hostedProgramList')}
            </span>
            <span className="rounded-full bg-[var(--color-fill-2)] px-2 py-0.5 text-xs text-[var(--color-text-2)]">
              {hostedCollectors.length}
            </span>
          </div>
        </div>
        <Table
          size="small"
          dataSource={collectorRows}
          columns={columns}
          pagination={false}
          rowKey="key"
          scroll={{ x: 520 }}
          locale={{
            emptyText: (
              <div className="py-6">
                <CompactEmptyState description={t('common.noData')} />
              </div>
            ),
          }}
        />
      </div>
    </div>
  );
};

export default NodeStatusWidget;
