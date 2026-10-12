'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Tag } from 'antd';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import { useTranslation } from '@/utils/i18n';
import type { SearchParams } from '@/app/monitor/types/search';
import { getRecentTimeRange } from '@/app/monitor/utils/common';
import { calculateQueryStep } from '@/app/monitor/utils/queryStep';
import { HorizontalBarPanel, TitleWithGuide } from '../../shared/widgets';
import { dashboardQueryCapabilityId } from '../../shared/utils/query-capability';
import { formatMetricValue } from '../../shared/utils/format';
import { latestFiniteValue } from '../../shared/utils/top-bars';
import styles from './index.module.scss';
import { HOST_FLEET_NIC_ERROR_QUERY } from './queries';
import {
  averageDisplayMetric,
  fleetHintGroups,
  FLEET_TOP_N,
  hostRowLabel,
  isHostListUnhealthy,
  logicalInstanceId,
  rankDisplayMetric
} from './fleet-rank';

const PAGE_SIZE = 200;
const MAX_ROWS = 2000;
/** 列表页没有范围选择器，网卡错误 cps 固定看最近 1 小时，与表内最新值同屏对照。 */
const NIC_WINDOW_MINUTES = 60;

interface HostFleetOverviewProps {
  objectId: React.Key;
}

/**
 * 主机舰队条：瓷砖 + Top N + 示意标签。
 * CPU/内存/磁盘% 直接用实例列表 display_fields 做客户端排序。
 * 网卡错误不在 display_fields，且 openspec get_host_resource_top 未接入本页、也不含 cps，
 * 因此对已拉到的实例再查一条合计速率后在前端排序。
 */
export default function HostFleetOverview({ objectId }: HostFleetOverviewProps) {
  const { t } = useTranslation();
  const { getInstanceList, getMonitorAlert } = useMonitorApi();
  const { getInstanceQuery } = useViewApi();
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [total, setTotal] = useState(0);
  const [truncated, setTruncated] = useState(false);
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const [nicBars, setNicBars] = useState<ReturnType<typeof rankDisplayMetric>>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!objectId) return;
    let active = true;
    const load = async () => {
      setLoading(true);
      try {
        const collected: Array<Record<string, unknown>> = [];
        let count = 0;
        let page = 1;
        while (collected.length < MAX_ROWS) {
          const data = await getInstanceList(objectId, {
            page,
            page_size: PAGE_SIZE,
            add_metrics: true
          });
          const batch = Array.isArray(data?.results) ? data.results : [];
          count = typeof data?.count === 'number' ? data.count : collected.length + batch.length;
          collected.push(...batch);
          if (batch.length < PAGE_SIZE || collected.length >= count) break;
          page += 1;
        }
        if (!active) return;
        const limited = collected.slice(0, MAX_ROWS);
        setRows(limited);
        setTotal(count);
        setTruncated(count > limited.length);

        // 告警列表实际按逗号分隔的 status_in 过滤；类型写成 string[]，与现有告警页一样传 'new'。
        const alertData = await getMonitorAlert({
          monitor_object_id: objectId,
          status_in: 'new',
          page: 1,
          page_size: 1
        } as unknown as Parameters<typeof getMonitorAlert>[0]);
        if (active) setAlertCount(typeof alertData?.count === 'number' ? alertData.count : 0);

        const instanceIds = limited
          .map((row) => String(row.instance_id || ''))
          .filter(Boolean);
        if (!instanceIds.length) {
          setNicBars([]);
          return;
        }
        const range = getRecentTimeRange({ timeRange: [], originValue: NIC_WINDOW_MINUTES });
        const start = range[0];
        const end = range[1];
        const nicParams: SearchParams = {
          capability_id: dashboardQueryCapabilityId(HOST_FLEET_NIC_ERROR_QUERY),
          monitor_object_id: objectId,
          instance_ids: instanceIds,
          source_unit: 'cps',
          auto_convert_unit: false,
          start,
          end,
          step: calculateQueryStep(start, end)
        };
        const nicRaw = await getInstanceQuery(nicParams);
        if (!active) return;
        const nameByLogicalId = new Map(
          limited.map((row) => [logicalInstanceId(row), hostRowLabel(row)])
        );
        const ranked = ((nicRaw as { data?: { result?: Array<{ metric?: Record<string, string>; values?: Array<[number, string]> }> } })?.data?.result || [])
          .map((series) => {
            const logicalId = String(series.metric?.instance_id || '').trim();
            const value = latestFiniteValue(series.values);
            return {
              label: nameByLogicalId.get(logicalId) || logicalId || '--',
              value
            };
          })
          .filter((item) => item.label && Number.isFinite(item.value))
          .sort((left, right) => right.value - left.value)
          .slice(0, FLEET_TOP_N);
        const peak = ranked.length ? Math.max(...ranked.map((item) => item.value)) : 0;
        const max = peak > 0 ? peak : 1;
        setNicBars(ranked.map((item) => {
          const formatted = formatMetricValue(item.value, 'cps');
          return {
            label: item.label,
            value: item.value,
            display: `${formatted.value}${formatted.unit || ''}`,
            color: 'var(--color-error)',
            max
          };
        }));
      } catch {
        if (!active) return;
        setNicBars([]);
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [getInstanceList, getInstanceQuery, getMonitorAlert, objectId]);

  const unhealthy = useMemo(
    () => rows.filter((row) => isHostListUnhealthy(row.status)).length,
    [rows]
  );
  const avgCpu = useMemo(() => averageDisplayMetric(rows, 'cpu_usage_total'), [rows]);
  const hints = useMemo(() => fleetHintGroups(rows), [rows]);
  const cpuBars = useMemo(() => rankDisplayMetric(rows, 'cpu_usage_total', 'percent'), [rows]);
  const memBars = useMemo(() => rankDisplayMetric(rows, 'mem_used_percent', 'percent'), [rows]);
  const diskBars = useMemo(() => rankDisplayMetric(rows, 'disk_used_percent', 'percent'), [rows]);
  const avgText = avgCpu == null ? '--' : `${avgCpu.toFixed(0)}%`;
  const scopeNote = truncated ? `已按前 ${rows.length} 台排序` : '与列表状态列一致';

  const tiles = [
    { label: '主机总数', value: String(total), hint: '实例计数', color: 'var(--color-text-1)' },
    { label: '告警数', value: alertCount == null ? '--' : String(alertCount), hint: '未恢复告警', color: 'var(--color-error)' },
    { label: '不健康数', value: String(unhealthy), hint: truncated ? `${scopeNote} · 失联` : '列表上报状态为失联', color: 'var(--color-warning)' },
    { label: '平均 CPU', value: avgText, hint: 'cpu_usage_total', color: 'var(--color-primary)' }
  ];

  return (
    <section className="mb-3" aria-label="主机舰队概览">
      <div className={styles.fleetStrip}>
        {tiles.map((tile) => (
          <div key={tile.label} className={`${styles.panel} ${styles.fleetTile}`}>
            <div className={styles.fleetTileLabel}>{tile.label}</div>
            <div className={styles.fleetTileValue} style={{ color: tile.color }}>{tile.value}</div>
            <div className={styles.fleetTileHint}>{tile.hint}</div>
          </div>
        ))}
      </div>
      <div className={styles.fleetHints}>
        {hints.map((group) => (
          <span key={group.label} className={styles.fleetHintGroup}>
            <span className={styles.fleetTileHint}>{group.label}</span>
            {group.values.map((value) => (
              <Tag key={`${group.label}-${value}`} bordered={false}>{value}</Tag>
            ))}
          </span>
        ))}
        <span className={styles.fleetTileHint}>
          标签只展示已有云区域或摘要字段，不做任意标签分面。列过滤仍用下方主机表。
        </span>
      </div>
      <div className={styles.fleetTop}>
        <HorizontalBarPanel
          styles={styles}
          className={styles.panel}
          title={<TitleWithGuide styles={styles} title="Top N · CPU" items={[{ label: 'CPU', detail: 'cpu_usage_total，取实例列表展示列。' }]} />}
          subtitle={loading ? t('common.loading') : 'cpu_usage_total'}
          items={cpuBars}
        />
        <HorizontalBarPanel
          styles={styles}
          className={styles.panel}
          title={<TitleWithGuide styles={styles} title="Top N · 内存" items={[{ label: '内存', detail: 'mem_used_percent，取实例列表展示列。' }]} />}
          subtitle="mem_used_percent"
          items={memBars}
        />
        <HorizontalBarPanel
          styles={styles}
          className={styles.panel}
          title={<TitleWithGuide styles={styles} title="Top N · 磁盘%" items={[{ label: '磁盘', detail: 'disk_used_percent，与列表磁盘列同一口径。' }]} />}
          subtitle="disk_used_percent"
          items={diskBars}
        />
        <HorizontalBarPanel
          styles={styles}
          className={styles.panel}
          title={<TitleWithGuide styles={styles} title="Top N · 网卡错误" items={[{ label: '网卡错误', detail: 'net_err_in_rate + net_err_out_rate，单位 cps（次/秒），不是百分比。' }]} />}
          subtitle="cps · 最近 1 小时"
          items={nicBars}
        />
      </div>
    </section>
  );
}
