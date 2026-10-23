'use client';
import React, { useEffect, useState, useRef } from 'react';
import { Button, Select, Tag, message } from 'antd';
import { useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import { fetchAllMonitorMetrics } from '@/app/monitor/api/fetchMetricCatalogPages';
import useEventApi from '@/app/monitor/api/event';
import useIntegrationApi from '@/app/monitor/api/integration';
import Permission from '@/components/permission';
import { StatusToneBadge } from '@/app/monitor/utils/statusTone';
import { useTranslation } from '@/utils/i18n';
import { ColumnItem, Pagination, TableDataItem } from '@/app/monitor/types';
import { ViewModalProps } from '@/app/monitor/types/view';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { INIT_VIEW_MODAL_FORM } from '@/app/monitor/constants/view';
import { buildMonitorStrategyDetailUrl } from '@/app/monitor/utils/policyRouteUtils';
import {
  PolicyMetricCatalogItem,
  resolvePolicyMetricDisplayName
} from '@/app/monitor/utils/policyDisplayName';

const MonitorPolicy: React.FC<ViewModalProps> = ({
  monitorObject,
  monitorName,
  form = INIT_VIEW_MODAL_FORM,
  readOnly = false,
  fillContainer = false,
}) => {
  const { isLoading } = useApiClient();
  const { getMonitorMetrics } = useMonitorApi();
  const { getMonitorPolicy } = useEventApi();
  const { getPolicyGroupMembership, joinPolicyGroup, leavePolicyGroup } = useIntegrationApi();
  const { t } = useTranslation();
  const router = useRouter();
  const { convertToLocalizedTime } = useLocalizedTime();
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef<number>(0);
  const getMonitorMetricsRef = useRef(getMonitorMetrics);
  getMonitorMetricsRef.current = getMonitorMetrics;
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [metricCatalog, setMetricCatalog] = useState<PolicyMetricCatalogItem[]>(
    []
  );
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  });
  const [membership, setMembership] = useState<{
    state: string | null;
    group_id: number | null;
    group_name: string;
    groups: Array<{ id: number; name: string; is_default?: boolean }>;
    legacy_policies: Array<{ id: number; name: string; enable: boolean }>;
  } | null>(null);
  const [nextGroupId, setNextGroupId] = useState<number | undefined>();

  const columns: ColumnItem[] = [
    {
      title: t('common.name'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (_, record) => {
        const name = String(record.name || '--');
        return !readOnly ? (
          <Button
            type="link"
            className="block min-w-0 max-w-full overflow-hidden px-0 text-left text-ellipsis whitespace-nowrap"
            title={name}
            onClick={() => linkToStrategyDetail(record)}
          >
            {name}
          </Button>
        ) : (
          <EllipsisWithTooltip
            text={name}
            className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          />
        );
      }
    },
    {
      title: t('monitor.events.enableStatus'),
      dataIndex: 'enable',
      key: 'enable',
      width: 120,
      ellipsis: true,
      render: (_, { enable }) => {
        if (enable && membership?.state === 'member') {
          return <StatusToneBadge tone="warning" label="仍会告警" />;
        }
        return enable ? (
          <Tag color="success">{t('monitor.events.turnedOn')}</Tag>
        ) : (
          <Tag>{t('monitor.events.inactive')}</Tag>
        );
      }
    },
    {
      title: t('monitor.events.policyMetric'),
      dataIndex: 'query_condition',
      key: 'query_condition',
      render: (_, record) => (
        <>{resolvePolicyMetricDisplayName(record, metricCatalog) || '--'}</>
      )
    },
    {
      title: t('monitor.events.alertName'),
      dataIndex: 'alert_name',
      key: 'alert_name',
      render: (_, { alert_name }) => <>{alert_name || '--'}</>
    },
    {
      title: t('monitor.events.executionTime'),
      dataIndex: 'last_run_time',
      key: 'last_run_time',
      width: 170,
      render: (_, { last_run_time }) => (
        <>{last_run_time ? convertToLocalizedTime(last_run_time) : '--'}</>
      )
    }
  ];

  useEffect(() => {
    if (isLoading) return;
    getBoundPolicies();
    const instanceId = String(form.instance_id || '').trim();
    if (!instanceId) {
      setMembership(null);
      return;
    }
    getPolicyGroupMembership(instanceId)
      .then((data) => {
        setMembership(data);
        setNextGroupId(data?.group_id || data?.groups?.[0]?.id);
      })
      .catch(() => setMembership(null));
  }, [isLoading, pagination.current, pagination.pageSize, form.instance_id, monitorObject]);

  useEffect(() => {
    if (isLoading || !monitorObject) {
      setMetricCatalog([]);
      return;
    }
    const abortController = new AbortController();
    fetchAllMonitorMetrics(
      getMonitorMetricsRef.current,
      { monitor_object_id: monitorObject },
      { signal: abortController.signal }
    )
      .then((data) => {
        if (abortController.signal.aborted) return;
        setMetricCatalog(data.items || []);
      })
      .catch(() => {
        if (abortController.signal.aborted) return;
        setMetricCatalog([]);
      });
    return () => abortController.abort();
  }, [isLoading, monitorObject]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const linkToStrategyDetail = (record: TableDataItem) => {
    router.push(
      buildMonitorStrategyDetailUrl('edit', {
        monitorObjId: String(monitorObject),
        monitorName,
        id: record.id as string | number,
        name: String(record.name || '')
      })
    );
  };

  const handleTableChange = (nextPagination: Pagination) => {
    setPagination(nextPagination);
  };

  const getBoundPolicies = async () => {
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    const currentRequestId = ++requestIdRef.current;
    const instanceId = String(form.instance_id || '').trim();
    if (!instanceId || !monitorObject) {
      setTableData([]);
      setPagination((pre) => ({ ...pre, total: 0 }));
      setTableLoading(false);
      return;
    }
    try {
      setTableLoading(true);
      const data = await getMonitorPolicy(
        '',
        {
          page: pagination.current,
          page_size: pagination.pageSize,
          monitor_object_id: monitorObject,
          monitor_instance_id: instanceId
        },
        { signal: abortController.signal }
      );
      if (currentRequestId !== requestIdRef.current) return;
      setTableData(data.items || []);
      setPagination((pre) => ({
        ...pre,
        total: data.count || 0
      }));
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setTableLoading(false);
      }
    }
  };

  const membershipState = membership?.state;
  const isMember = membershipState === 'member';
  const membershipBadge = isMember
    ? '在组'
    : membershipState === 'declined'
      ? '不自动入组'
      : membershipState === 'skipped'
        ? '未入组'
        : membershipState === 'failed'
          ? '加入失败'
          : '无记录';
  const membershipTone = isMember
    ? 'success'
    : membershipState === 'declined'
      ? 'warning'
      : membershipState === 'failed'
        ? 'fail'
        : 'neutral';
  const membershipHint = isMember
    ? ''
    : membershipState === 'failed'
      ? '采集已完成，可以在这里重新加入。'
      : membershipState === 'declined'
        ? '这台实例不会自动加入策略组。'
        : '还没有加入策略组。';
  const legacyPolicies = membership?.legacy_policies || [];
  const legacyHint = isMember
    ? '未停用的会和策略组一起告警。要停用，去单策略列表改是否生效。'
    : '这些策略直接覆盖这台实例，不经过策略组。';

  const refreshMembership = () => {
    const instanceId = String(form.instance_id || '').trim();
    if (!instanceId) return;
    getPolicyGroupMembership(instanceId).then((data) => {
      setMembership(data);
      setNextGroupId(data?.group_id || data?.groups?.[0]?.id);
    });
  };

  return (
    <div className={fillContainer ? 'flex h-full min-h-0 w-full flex-col' : 'w-full'}>
      {!readOnly && membership ? (
        <div className="mb-3 flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-3 py-2.5">
            <div className="flex min-w-0 items-center gap-2">
              <span className="shrink-0 text-[13px] font-semibold text-[var(--color-text-1)]">策略组</span>
              <StatusToneBadge tone={membershipTone} label={membershipBadge} />
              {isMember ? (
                <span className="min-w-0 truncate text-sm text-[var(--color-text-1)]">{membership.group_name || '--'}</span>
              ) : (
                <span className="text-xs leading-5 text-[var(--color-text-3)]">{membershipHint}</span>
              )}
            </div>
            <Permission requiredPermissions={['Edit']} permissionPath="/monitor/event/strategy">
              <div className="flex flex-wrap items-center gap-2">
                <Select
                  className="w-[220px]"
                  value={nextGroupId}
                  options={(membership.groups || []).map((item) => ({
                    value: item.id,
                    label: item.is_default ? `${item.name}（默认）` : item.name
                  }))}
                  onChange={setNextGroupId}
                />
                <Button
                  type="primary"
                  disabled={!nextGroupId}
                  onClick={async () => {
                    if (!nextGroupId) return;
                    await joinPolicyGroup(nextGroupId, [String(form.instance_id)]);
                    message.success(isMember ? '已更换策略组，原规则未恢复告警会结束' : '已加入策略组');
                    refreshMembership();
                  }}
                >
                  {isMember ? '更换' : '加入'}
                </Button>
                {isMember ? (
                  <Button
                    onClick={async () => {
                      await leavePolicyGroup([String(form.instance_id)]);
                      message.success('已退出，未恢复告警会结束');
                      refreshMembership();
                    }}
                  >
                    退出
                  </Button>
                ) : null}
              </div>
            </Permission>
          </div>
        </div>
      ) : null}
      {!readOnly && legacyPolicies.length ? (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-[13px] font-semibold text-[var(--color-text-1)]">单策略</span>
          <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-1.5 text-xs font-semibold tabular-nums text-[var(--color-primary)]">
            {legacyPolicies.length}
          </span>
          <span className="text-xs leading-5 text-[var(--color-text-3)]">{legacyHint}</span>
        </div>
      ) : null}
      <CustomTable
        tableLayout="fixed"
        scroll={fillContainer ? { x: 890 } : { y: 'calc(100vh - 360px)', x: 890 }}
        columns={columns}
        dataSource={tableData}
        pagination={pagination}
        loading={tableLoading}
        rowKey="id"
        locale={{ emptyText: t('monitor.views.noBoundPolicy') }}
        onChange={handleTableChange}
      />
    </div>
  );
};

export default MonitorPolicy;
