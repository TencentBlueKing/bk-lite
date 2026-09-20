'use client';

import React, { useMemo } from 'react';
import { Table } from 'antd';
import type { TableColumnsType } from 'antd';
import { DashboardPanel } from '../../shared/widgets';
import { formatEnumValue, formatMetricValue } from '../../shared/utils/format';
import type { MetricEnumMap, MetricUnit } from '../../shared/types';
import type { PreparedChartPanel } from '../common/simple-dashboard-core';
import type { DashboardStyles } from '../common/dashboard-components';
import { HEALTH_ENUM, LINK_ENUM } from './config';

interface DimensionRow {
  rowKey: string;
  value: number;
  labels: Record<string, string>;
}

interface JoinedRow {
  joinKey: string;
  labels: Record<string, string>;
  values: Record<string, number>;
}

const latestDimensionRows = (chart?: PreparedChartPanel): DimensionRow[] => {
  const latest = chart?.data?.[chart.data.length - 1];
  if (!latest) return [];
  return Object.keys(latest)
    .filter((key) => /^value\d+$/.test(key))
    .sort()
    .map((key) => {
      const details = latest.details?.[key] || [];
      const labels: Record<string, string> = {};
      for (const item of details) {
        if (item.name && item.name !== 'instance_name' && item.name !== 'instance_id') {
          labels[item.name] = item.value;
        }
      }
      return {
        rowKey: key,
        value: Number(latest[key]),
        labels
      };
    })
    .filter((row) => Number.isFinite(row.value));
};

const joinByLabels = (
  sources: Array<{ metric: string; rows: DimensionRow[] }>,
  keyNames: string[]
): JoinedRow[] => {
  const map = new Map<string, JoinedRow>();
  for (const source of sources) {
    for (const row of source.rows) {
      const joinKey = keyNames.map((name) => row.labels[name] || '').join('\0') || row.rowKey;
      const current = map.get(joinKey) || { joinKey, labels: {}, values: {} };
      current.labels = { ...current.labels, ...row.labels };
      current.values[source.metric] = row.value;
      map.set(joinKey, current);
    }
  }
  return [...map.values()];
};

const findChart = (charts: PreparedChartPanel[], title: string) =>
  charts.find((item) => item.chart.title === title);

const formatQuantity = (value: number | undefined, unit: MetricUnit, suffix?: string) => {
  if (value == null || !Number.isFinite(value)) return '--';
  const formatted = formatMetricValue(value, unit);
  const body = `${formatted.value}${formatted.unit || ''}`;
  return suffix ? `${body} ${suffix}` : body;
};

const StatusText = ({
  value,
  enumMap,
  styles
}: {
  value?: number;
  enumMap: MetricEnumMap;
  styles: DashboardStyles;
}) => {
  const mapped = formatEnumValue(value ?? Number.NaN, enumMap);
  return (
    <span className={styles.statusCell}>
      {mapped.color ? (
        <span className={styles.statusDot} style={{ background: mapped.color }} />
      ) : null}
      <span style={mapped.color ? { color: mapped.color } : undefined}>{mapped.value}</span>
    </span>
  );
};

const DimensionTablePanel = <T extends { joinKey: string }>({
  title,
  subtitle,
  guide,
  columns,
  rows,
  styles,
  spanClass
}: {
  title: string;
  subtitle: string;
  guide: Array<{ label: string; detail: string }>;
  columns: TableColumnsType<T>;
  rows: T[];
  styles: DashboardStyles;
  spanClass: string;
}) => {
  if (!rows.length) return null;
  return (
    <DashboardPanel
      title={title}
      subtitle={subtitle}
      guide={guide}
      styles={styles}
      className={`${spanClass} ${styles.dimTablePanel}`}
      bodyClassName={styles.dimTableWrap}
    >
      <Table<T>
        columns={columns}
        dataSource={rows}
        rowKey={(row) => row.joinKey}
        pagination={false}
        size="small"
      />
    </DashboardPanel>
  );
};

export const extractFirmwareLabel = (charts: PreparedChartPanel[]) => {
  const labels = latestDimensionRows(findChart(charts, '固件资产'))[0]?.labels || {};
  const chips = [
    labels.bmc_firmware ? `BMC ${labels.bmc_firmware}` : '',
    labels.bios_version ? `BIOS ${labels.bios_version}` : ''
  ].filter(Boolean);
  return chips.join(' · ') || undefined;
};

export type HardwareTableKind = 'fan' | 'psu' | 'nic' | 'storage';

export function HardwareDimensionTables({
  charts,
  styles,
  include
}: {
  charts: PreparedChartPanel[];
  styles: DashboardStyles;
  include?: HardwareTableKind[];
}) {
  const visible = new Set(include || ['fan', 'psu', 'nic', 'storage']);
  const fanRows = useMemo(() => {
    const speed = latestDimensionRows(findChart(charts, '风扇转速'));
    const health = latestDimensionRows(findChart(charts, '风扇健康'));
    return joinByLabels(
      [
        { metric: 'speed', rows: speed },
        { metric: 'health', rows: health }
      ],
      ['name']
    );
  }, [charts]);

  const psuRows = useMemo(() => {
    const health = latestDimensionRows(findChart(charts, '电源健康'));
    const watts = latestDimensionRows(findChart(charts, '电源输入功率'));
    const volts = latestDimensionRows(findChart(charts, '电源输入电压'));
    return joinByLabels(
      [
        { metric: 'health', rows: health },
        { metric: 'watts', rows: watts },
        { metric: 'volts', rows: volts }
      ],
      ['name']
    );
  }, [charts]);

  const nicRows = useMemo(() => {
    const link = latestDimensionRows(findChart(charts, '网口链路'));
    const health = latestDimensionRows(findChart(charts, '网口健康'));
    const speed = latestDimensionRows(findChart(charts, '网口速率'));
    return joinByLabels(
      [
        { metric: 'link', rows: link },
        { metric: 'health', rows: health },
        { metric: 'speed', rows: speed }
      ],
      ['adapter_id', 'id']
    );
  }, [charts]);

  const storageRows = useMemo(() => {
    const storage = latestDimensionRows(findChart(charts, '存储健康'));
    const controllers = latestDimensionRows(findChart(charts, '控制器健康'));
    const byStorage = new Map<string, JoinedRow>();
    for (const row of storage) {
      const id = row.labels.id || row.rowKey;
      byStorage.set(id, {
        joinKey: id,
        labels: { storage_id: id },
        values: { storage: row.value }
      });
    }
    for (const row of controllers) {
      const storageId = row.labels.storage_id || row.labels.id || row.rowKey;
      const current = byStorage.get(storageId) || {
        joinKey: storageId,
        labels: { storage_id: storageId },
        values: {}
      };
      const controllerName = row.labels.id || '';
      const existing = current.labels.controller ? `${current.labels.controller}, ${controllerName}` : controllerName;
      current.labels = { ...current.labels, controller: existing };
      const worst = current.values.controller == null
        ? row.value
        : Math.max(current.values.controller, row.value);
      current.values.controller = worst;
      byStorage.set(storageId, current);
    }
    return [...byStorage.values()];
  }, [charts]);

  const fanColumns: TableColumnsType<JoinedRow> = [
    { title: '风扇', dataIndex: ['labels', 'name'], key: 'name', render: (value?: string) => value || '--' },
    {
      title: '转速',
      key: 'speed',
      align: 'right',
      render: (_, row) => formatQuantity(row.values.speed, 'none', 'RPM')
    },
    {
      title: '健康',
      key: 'health',
      render: (_, row) => <StatusText value={row.values.health} enumMap={HEALTH_ENUM} styles={styles} />
    }
  ];

  const psuColumns: TableColumnsType<JoinedRow> = [
    { title: '电源', dataIndex: ['labels', 'name'], key: 'name', render: (value?: string) => value || '--' },
    {
      title: '健康',
      key: 'health',
      render: (_, row) => <StatusText value={row.values.health} enumMap={HEALTH_ENUM} styles={styles} />
    },
    {
      title: '输入功率',
      key: 'watts',
      align: 'right',
      render: (_, row) => formatQuantity(row.values.watts, 'watts')
    },
    {
      title: '输入电压',
      key: 'volts',
      align: 'right',
      render: (_, row) => formatQuantity(row.values.volts, 'volts')
    }
  ];

  const nicColumns: TableColumnsType<JoinedRow> = [
    {
      title: '适配器',
      dataIndex: ['labels', 'adapter_id'],
      key: 'adapter',
      render: (value?: string) => value || '--'
    },
    { title: '端口', dataIndex: ['labels', 'id'], key: 'port', render: (value?: string) => value || '--' },
    {
      title: '健康',
      key: 'health',
      render: (_, row) => <StatusText value={row.values.health} enumMap={HEALTH_ENUM} styles={styles} />
    },
    {
      title: '链路',
      key: 'link',
      render: (_, row) => <StatusText value={row.values.link} enumMap={LINK_ENUM} styles={styles} />
    },
    {
      title: '速率',
      key: 'speed',
      align: 'right',
      render: (_, row) => formatQuantity(row.values.speed, 'none', 'Mbps')
    }
  ];

  const storageColumns: TableColumnsType<JoinedRow> = [
    {
      title: '存储',
      dataIndex: ['labels', 'storage_id'],
      key: 'storage',
      render: (value?: string) => value || '--'
    },
    {
      title: '子系统健康',
      key: 'storageHealth',
      render: (_, row) => <StatusText value={row.values.storage} enumMap={HEALTH_ENUM} styles={styles} />
    },
    {
      title: '控制器',
      dataIndex: ['labels', 'controller'],
      key: 'controller',
      render: (value?: string) => value || '--'
    },
    {
      title: '控制器健康',
      key: 'controllerHealth',
      render: (_, row) => <StatusText value={row.values.controller} enumMap={HEALTH_ENUM} styles={styles} />
    }
  ];

  return (
    <>
      {visible.has('fan') ? (
        <DimensionTablePanel
          title="风扇健康"
          subtitle="转速与 Status.Health"
          guide={[{ label: '风扇', detail: '按风扇名称对齐转速与健康；缺健康样本时只保留转速。' }]}
          columns={fanColumns}
          rows={fanRows}
          styles={styles}
          spanClass={styles.span6}
        />
      ) : null}
      {visible.has('psu') ? (
        <DimensionTablePanel
          title="电源模块"
          subtitle="健康、输入功率与电压"
          guide={[{ label: '电源', detail: '热备电源输入功率通常接近 0 W，健康仍应为 OK。' }]}
          columns={psuColumns}
          rows={psuRows}
          styles={styles}
          spanClass={styles.span6}
        />
      ) : null}
      {visible.has('nic') ? (
        <DimensionTablePanel
          title="网口"
          subtitle="Chassis NetworkPorts · 不爬 EthernetInterfaces"
          guide={[{ label: '网口', detail: '适配器 + 端口对齐链路、健康与速率。' }]}
          columns={nicColumns}
          rows={nicRows}
          styles={styles}
          spanClass={styles.span6}
        />
      ) : null}
      {visible.has('storage') ? (
        <DimensionTablePanel
          title="存储子系统"
          subtitle="HealthRollup + 内嵌控制器 · 不逐盘"
          guide={[
            {
              label: '存储',
              detail: '覆盖控制器/子系统故障。逐盘 Status.Health 需要 GET /drives，当前采集禁止。'
            }
          ]}
          columns={storageColumns}
          rows={storageRows}
          styles={styles}
          spanClass={styles.span12}
        />
      ) : null}
    </>
  );
}
