'use client';
import React, { useEffect, useState, useRef } from 'react';
import { Button, Tag } from 'antd';
import { useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import { fetchAllMonitorMetrics } from '@/app/monitor/api/fetchMetricCatalogPages';
import useEventApi from '@/app/monitor/api/event';
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
  form = INIT_VIEW_MODAL_FORM
}) => {
  const { isLoading } = useApiClient();
  const { getMonitorMetrics } = useMonitorApi();
  const { getMonitorPolicy } = useEventApi();
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

  const columns: ColumnItem[] = [
    {
      title: t('common.name'),
      dataIndex: 'name',
      key: 'name',
      render: (_, record) => (
        <Button type="link" className="px-0" onClick={() => linkToStrategyDetail(record)}>
          {record.name || '--'}
        </Button>
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

  return (
    <div className="w-full">
      <CustomTable
        scroll={{ y: 'calc(100vh - 360px)', x: 890 }}
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
