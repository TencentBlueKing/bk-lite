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
import { useTranslation } from '@/utils/i18n';
import { ColumnItem, Pagination, TableDataItem } from '@/app/monitor/types';
import { ViewModalProps } from '@/app/monitor/types/view';
import CustomTable from '@/components/custom-table';
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
      render: (_, record) =>
        !readOnly ? (
          <Button type="link" className="px-0" onClick={() => linkToStrategyDetail(record)}>
            {record.name || '--'}
          </Button>
        ) : (
          <span>{record.name || '--'}</span>
        )
    },
    {
      title: t('monitor.events.enableStatus'),
      dataIndex: 'enable',
      key: 'enable',
      width: 110,
      render: (_, { enable }) =>
        enable ? (
          <Tag color="success">{t('monitor.events.turnedOn')}</Tag>
        ) : (
          <Tag>{t('monitor.events.inactive')}</Tag>
        )
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

  const stateLabel =
    membership?.state === 'member'
      ? membership.group_name || '在组'
      : membership?.state === 'declined'
        ? '不自动入组'
        : membership?.state === 'skipped'
          ? '未入组'
          : '无记录';

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
        <div className="mb-3 rounded border border-[var(--color-border-2)] p-3">
          <div className="mb-2">所属策略组：{stateLabel}</div>
          {(membership.legacy_policies || []).map((item) => (
            <div key={item.id} className="mb-1 text-[12px]">
              {item.name}
              {item.enable ? ' 仍会和策略组一起告警' : ' 已停用'}
            </div>
          ))}
          <Permission requiredPermissions={['Edit']} permissionPath="/monitor/event/strategy">
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Select
                className="min-w-[220px]"
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
                  message.success(membership.state === 'member' ? '已更换策略组，原规则未恢复告警会结束' : '已加入策略组');
                  refreshMembership();
                }}
              >
                {membership.state === 'member' ? '更换' : '加入'}
              </Button>
              {membership.state === 'member' ? (
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
      ) : null}
      <CustomTable
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
