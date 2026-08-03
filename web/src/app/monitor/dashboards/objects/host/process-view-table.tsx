'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Progress, Table } from 'antd';
import type { TableColumnsType } from 'antd';
import { useRouter } from 'next/navigation';
import useViewApi from '@/app/monitor/api/view';
import useMonitorApi from '@/app/monitor/api';
import { DashboardPanel } from '../../shared/widgets';
import { buildSearchParams, formatMetricValue } from '../../shared/utils';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';

interface ProcessViewRow {
  key: string;
  processName: string;
  portAlive: number | null;
  cpuUsage: number | null;
  memUsage: number | null;
}

interface ProcessViewTableProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  styles: Record<string, string>;
}

type InstantVector = {
  metric?: Record<string, string>;
  value?: [number | string, string];
};

const PROCESS_CPU_QUERY =
  'sum(procstat_cpu_usage{instance_type="process", __$labels__}) by (instance_id, process_name)';
const PROCESS_MEM_QUERY =
  'sum(procstat_memory_usage{instance_type="process", __$labels__}) by (instance_id, process_name)';
const PROCESS_PORT_QUERY =
  '((floor(((avg(clamp_max(net_response_result_code{instance_type="process", __$labels__}, 1) == bool 0) by (instance_id, process_name)) or process_port_alive{instance_type="process", __$labels__})) + ceil(((avg(clamp_max(net_response_result_code{instance_type="process", __$labels__}, 1) == bool 0) by (instance_id, process_name)) or process_port_alive{instance_type="process", __$labels__}))) / 2)';

const parseInstantMap = (payload: any): Map<string, number> => {
  const map = new Map<string, number>();
  const results: InstantVector[] = payload?.data?.result || [];
  for (const item of results) {
    const name = String(item.metric?.process_name || '').trim();
    if (!name) continue;
    const raw = item.value?.[1];
    if (raw == null || raw === '') continue;
    const num = Number(raw);
    if (!Number.isFinite(num)) continue;
    map.set(name, num);
  }
  return map;
};

const formatPercent = (value: number | null) => {
  if (value == null) return '--';
  const formatted = formatMetricValue(value, 'percent');
  return `${formatted.value}${formatted.unit || '%'}`;
};

const PortAliveCell = ({ value }: { value: number | null }) => {
  let color = '#8c8c8c';
  let label = '无数据';
  if (value != null) {
    if (value >= 1) {
      color = '#1ac44a';
      label = '存活';
    } else if (value <= 0) {
      color = '#ff4d4f';
      label = '失活';
    } else {
      color = '#faad14';
      label = '部分失活';
    }
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block h-2 w-2 rounded-full"
        style={{ background: color }}
        aria-hidden
      />
      <span>{label}</span>
    </span>
  );
};

const UsageCell = ({ value }: { value: number | null }) => {
  if (value == null) return <span>--</span>;
  const percent = Math.max(0, Math.min(100, value));
  return (
    <div className="flex min-w-[140px] items-center gap-2">
      <span className="w-[64px] text-right tabular-nums">{formatPercent(value)}</span>
      <Progress
        percent={percent}
        showInfo={false}
        size="small"
        strokeColor={percent >= 70 ? '#ff4d4f' : percent >= 40 ? '#faad14' : '#2f6bff'}
        className="mb-0 flex-1"
      />
    </div>
  );
};

export function HostProcessViewTable({ dashboard, styles }: ProcessViewTableProps) {
  const { getInstanceInstantQuery } = useViewApi();
  const { getMonitorObject } = useMonitorApi();
  const router = useRouter();
  const [rows, setRows] = useState<ProcessViewRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [processObjectId, setProcessObjectId] = useState<string>('');
  const idValuesKey = JSON.stringify(dashboard.idValues);
  const timeKey = JSON.stringify(dashboard.timeValues);
  const instanceIdKeys = useMemo(() => ['instance_id'], []);

  useEffect(() => {
    let active = true;
    getMonitorObject({ name: 'Process', include_invisible: true })
      .then((data: any) => {
        if (!active) return;
        const list = Array.isArray(data) ? data : data?.items || data?.results || [];
        const processObj = list.find((item: any) => item?.name === 'Process');
        if (processObj?.id != null) {
          setProcessObjectId(String(processObj.id));
        }
      })
      .catch(() => {
        if (active) setProcessObjectId('');
      });
    return () => {
      active = false;
    };
  }, [getMonitorObject]);

  useEffect(() => {
    if (!dashboard.isDashboardMode || !dashboard.idValues.length) {
      setRows([]);
      return;
    }

    let active = true;
    setLoading(true);
    const load = async () => {
      const common = [
        dashboard.idValues,
        instanceIdKeys,
        dashboard.timeValues,
      ] as const;
      const [cpuRes, memRes, portRes] = await Promise.all([
        getInstanceInstantQuery(
          buildSearchParams(PROCESS_CPU_QUERY, 'percent', ...common)
        ).catch(() => null),
        getInstanceInstantQuery(
          buildSearchParams(PROCESS_MEM_QUERY, 'percent', ...common)
        ).catch(() => null),
        getInstanceInstantQuery(
          buildSearchParams(PROCESS_PORT_QUERY, 'none', ...common)
        ).catch(() => null),
      ]);
      if (!active) return;

      const cpuMap = parseInstantMap(cpuRes);
      const memMap = parseInstantMap(memRes);
      const portMap = parseInstantMap(portRes);
      const names = new Set<string>([
        ...cpuMap.keys(),
        ...memMap.keys(),
        ...portMap.keys(),
      ]);
      const nextRows = Array.from(names)
        .sort((a, b) => a.localeCompare(b))
        .map((processName) => ({
          key: processName,
          processName,
          portAlive: portMap.has(processName) ? portMap.get(processName)! : null,
          cpuUsage: cpuMap.has(processName) ? cpuMap.get(processName)! : null,
          memUsage: memMap.has(processName) ? memMap.get(processName)! : null,
        }));
      setRows(nextRows);
      setLoading(false);
    };
    load();

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    dashboard.currentInstanceInterval,
    dashboard.isDashboardMode,
    dashboard.loadTick,
    getInstanceInstantQuery,
    idValuesKey,
    instanceIdKeys,
    timeKey,
  ]);

  const columns: TableColumnsType<ProcessViewRow> = [
    {
      title: '进程名称',
      dataIndex: 'processName',
      key: 'processName',
      ellipsis: true,
    },
    {
      title: '端口存活',
      dataIndex: 'portAlive',
      key: 'portAlive',
      width: 120,
      render: (value: number | null) => <PortAliveCell value={value} />,
    },
    {
      title: 'CPU使用率',
      dataIndex: 'cpuUsage',
      key: 'cpuUsage',
      width: 220,
      render: (value: number | null) => <UsageCell value={value} />,
    },
    {
      title: '应用内存使用率',
      dataIndex: 'memUsage',
      key: 'memUsage',
      width: 220,
      render: (value: number | null) => <UsageCell value={value} />,
    },
  ];

  const openProcessList = () => {
    if (!processObjectId) return;
    const hostInstanceId = dashboard.idValues[0] || dashboard.instanceId;
    const params = new URLSearchParams({
      object_id: processObjectId,
    });
    if (hostInstanceId) {
      params.set('vm_params.instance_id', String(hostInstanceId));
    }
    router.push(`/monitor/view?${params.toString()}`);
  };

  return (
    <DashboardPanel
      title={
        <span className="inline-flex w-full items-center justify-between gap-3">
          <span>进程视图</span>
          <Button type="link" size="small" disabled={!processObjectId} onClick={openProcessList}>
            进程列表
          </Button>
        </span>
      }
      subtitle="按主机 instance_id 关联的进程 CPU、内存与端口存活"
      guide={[
        {
          label: '关联方式',
          detail: '进程指标复用主机 instance_id，并按 process_name 展示各进程状态。',
        },
        {
          label: '端口存活',
          detail: '存活=全部端口可达；失活=全部不可达；部分失活=部分可达；无数据=未配置端口或无上报。',
        },
      ]}
      className={`${styles.span12}`}
      styles={styles}
    >
      <Table<ProcessViewRow>
        size="small"
        rowKey="key"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={false}
        locale={{ emptyText: loading ? '加载中' : '暂无进程监控数据' }}
      />
    </DashboardPanel>
  );
}
