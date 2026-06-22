'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { DatabaseOutlined, CloudServerOutlined, AppstoreOutlined, DeploymentUnitOutlined, PartitionOutlined, ReloadOutlined } from '@ant-design/icons';
import useViewApi from '@/app/monitor/api/view';
import useMonitorApi from '@/app/monitor/api';
import { ChartData, TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
import {
  buildSearchParams,
  runWithConcurrency,
  toMetricSeries,
  buildMetricItem,
  mergeChartSeries,
  getCollectionStatus,
  buildCollectionStatusTimeline,
  buildInstanceDisplayName,
  buildInstanceSearchTokens,
  normalizeDisplayText,
  isOpaqueIdentifier,
  parseLegacyParamList,
  formatMetricValue,
  buildPreviousPeriodTimeValues,
  getPeriodCompare,
  useLoadSequence
} from '../../shared/utils';
import {
  StatCard,
  CollectionStatusCard,
  TitleWithGuide,
  DashboardPageHeader,
  DashboardInstanceCard,
  RingChartPanel,
  HorizontalBarPanel,
  StackedBarPanel,
  TrendChartPanel
} from '../../shared/widgets';
import {
  QUERIES,
  QUERY_GROUPS,
  QUERY_CONCURRENCY,
  TREND_METRICS,
  TOP_N,
  HEALTH_GREEN,
  HEALTH_AMBER,
  HEALTH_RED,
  NEUTRAL_BLUE,
  NEUTRAL_INK,
  RING_REST,
  RING_DONE,
  NS_LABEL
} from './queries';
import {
  latestScalar,
  seriesLatestByLabel,
  phaseCount,
  saturationColor,
  buildTopBars,
  coresDisplay,
  bytesDisplay
} from './parse';
import styles from './index.module.scss';

interface InstanceOption {
  label: string;
  value: string;
  instanceIdValues: string[];
  searchTokens: string[];
  interval?: number;
}

type RawMap = Record<string, any>;

const num = (n: number) => formatMetricValue(n, 'counts').value;
const pct = (n: number) => `${n.toFixed(1)}%`;

// KPI 卡「较上一周期」需要拉取的上一周期序列(工作负载=三类之和)
const KPI_COMPARE_KEYS = ['nodesTotal', 'namespaces', 'podsTotal', 'deployTotal', 'dsTotal', 'stsTotal', 'crashloop'];

// 把若干时序按【时间戳】对齐相加(工作负载总数 = Deployment+StatefulSet+DaemonSet 的趋势)。
// 按时间戳而非数组下标聚合:某类工作负载样本稀疏/起始时间不同也不会错位。
const sumSeries = (arrs: ChartData[][]): ChartData[] => {
  const byTime = new Map<number, ChartData>();
  arrs.forEach((series) => {
    series.forEach((pt) => {
      const t = Number(pt.time);
      const prev = byTime.get(t);
      byTime.set(t, { time: pt.time, value1: (prev ? Number(prev.value1) || 0 : 0) + (Number(pt.value1) || 0) });
    });
  });
  return Array.from(byTime.values()).sort((a, b) => Number(a.time) - Number(b.time));
};

// 字节类指标(内存)需禁用服务端单位自动换算:服务端会把 bytes 缩放成 GiB,
// 前端 bytesDisplay 会再格式化一次,不禁用则双重换算导致数值小约 1e9 倍。
const RAW_VALUE_METRICS = new Set([
  'prometheus_remote_write_container_memory_working_set_bytes',
  'prometheus_remote_write_kube_node_status_allocatable',
  'prometheus_remote_write_kube_pod_container_resource_requests'
]);

export default function K8sClusterDashboardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getInstanceQuery } = useViewApi();
  const monitorApi = useMonitorApi();
  const getInstanceListRef = useRef(monitorApi.getInstanceList);
  useEffect(() => {
    getInstanceListRef.current = monitorApi.getInstanceList;
  });

  const monitorObjectId = searchParams.get('monitorObjId') || '';
  const rawInstanceId = searchParams.get('instance_id') || '';
  const parsedLegacy = parseLegacyParamList(rawInstanceId);
  const instanceId = parsedLegacy[0] || rawInstanceId || '';
  const instanceName = searchParams.get('instance_name') || '--';
  const idValues = useMemo(() => {
    const explicit = parseLegacyParamList(searchParams.get('instance_id_values'));
    if (explicit.length > 0) return explicit;
    if (parsedLegacy.length > 0) return parsedLegacy;
    const normalized = normalizeDisplayText(String(instanceId));
    return normalized ? [normalized] : [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);
  const instanceIdKeys = (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean);
  const idValuesKey = idValues.join('|');

  const resolvedInstanceName = isOpaqueIdentifier(instanceName) ? '' : normalizeDisplayText(instanceName);
  const objectFallbackName = 'K8s 集群';

  const [displayMode, setDisplayMode] = useState<'dashboard' | 'metrics'>('dashboard');
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({ timeRange: [], originValue: 15 });
  const timeDefaultValue: TimeSelectorDefaultValue = { selectValue: 15, rangePickerVaule: null };
  const [frequence, setFrequence] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [raw, setRaw] = useState<RawMap>({});
  const [previousRaw, setPreviousRaw] = useState<RawMap>({});
  const [instanceOptions, setInstanceOptions] = useState<InstanceOption[]>([]);
  const [instanceLoading, setInstanceLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const loadSequence = useLoadSequence();

  // 实例列表
  useEffect(() => {
    if (!monitorObjectId) {
      setInstanceOptions([]);
      return;
    }
    let active = true;
    (async () => {
      try {
        setInstanceLoading(true);
        const data = await getInstanceListRef.current(monitorObjectId, { page_size: -1 });
        if (!active) return;
        const map = new Map<string, InstanceOption>();
        (data?.results || []).forEach((item: any) => {
          const value = String(item.instance_id || '');
          if (!value || map.has(value)) return;
          const label = buildInstanceDisplayName(item);
          map.set(value, {
            label,
            value,
            instanceIdValues: Array.isArray(item.instance_id_values) && item.instance_id_values.length ? item.instance_id_values : [value],
            searchTokens: buildInstanceSearchTokens(item, label),
            interval: Number(item.interval) || undefined
          });
        });
        setInstanceOptions(Array.from(map.values()));
      } catch {
        if (active) setInstanceOptions([]);
      } finally {
        if (active) setInstanceLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [monitorObjectId]);

  const currentOption = instanceOptions.find((o) => o.value === String(instanceId));
  const currentInstanceInterval = currentOption?.interval;

  // 数据加载:hero 先到,面板后到
  const runGroup = async (keys: string[], tv: TimeValuesProps) =>
    runWithConcurrency(keys, QUERY_CONCURRENCY, async (key) => {
      const q = QUERIES[key];
      try {
        const result = await getInstanceQuery(buildSearchParams(q.query, q.unit, idValues, instanceIdKeys, tv, RAW_VALUE_METRICS, undefined, currentInstanceInterval));
        return [key, result] as const;
      } catch {
        return [key, null] as const;
      }
    });

  const loadAll = async (silent = false) => {
    const seq = loadSequence.begin();
    if (!silent) setLoading(true);
    const heroResults = await runGroup(QUERY_GROUPS.hero, timeValues);
    if (!loadSequence.isCurrent(seq)) return;
    setRaw((prev) => (silent ? { ...prev, ...Object.fromEntries(heroResults) } : Object.fromEntries(heroResults)));
    if (!silent) setLoading(false);
    runGroup(QUERY_GROUPS.panels, timeValues).then((panelResults) => {
      if (loadSequence.isCurrent(seq)) setRaw((prev) => ({ ...prev, ...Object.fromEntries(panelResults) }));
    });
    // KPI 卡「较上一周期」对比:取上一周期同样窗口的计数。
    const prevTv = buildPreviousPeriodTimeValues(timeValues);
    runGroup(KPI_COMPARE_KEYS, prevTv).then((prevResults) => {
      if (loadSequence.isCurrent(seq)) setPreviousRaw(Object.fromEntries(prevResults));
    });
  };

  useEffect(() => {
    if (idValues.length === 0) {
      setRaw({});
      setLoading(false);
      return;
    }
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentInstanceInterval, idValuesKey, timeValues]);

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (displayMode === 'dashboard' && frequence > 0) {
      timerRef.current = setInterval(() => loadAll(true), frequence);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frequence, timeValues, idValuesKey, displayMode]);

  // ── 派生数据 ──
  const d = useMemo(() => {
    const nodesReady = latestScalar(raw.nodesReady);
    const nodesTotal = latestScalar(raw.nodesTotal);
    const running = phaseCount(raw.podPhase, 'Running');
    const pending = phaseCount(raw.podPhase, 'Pending');
    const failed = phaseCount(raw.podPhase, 'Failed');
    const succeeded = phaseCount(raw.podPhase, 'Succeeded');
    const podsTotal = latestScalar(raw.podsTotal);
    const namespaces = latestScalar(raw.namespaces);
    const wlTotal = latestScalar(raw.deployTotal) + latestScalar(raw.dsTotal) + latestScalar(raw.stsTotal);
    const wlDegraded = latestScalar(raw.deployDegraded) + latestScalar(raw.dsDegraded) + latestScalar(raw.stsDegraded);
    const wlAvailable = Math.max(wlTotal - wlDegraded, 0);
    const memPct = latestScalar(raw.memPct);
    const cpuPct = latestScalar(raw.cpuPct);
    const diskPct = latestScalar(raw.diskPct);
    const crashloop = latestScalar(raw.crashloop);
    const restarts1h = latestScalar(raw.restarts1h);
    return {
      nodesReady, nodesTotal, running, pending, failed, succeeded, podsTotal, namespaces,
      wlTotal, wlDegraded, wlAvailable, memPct, cpuPct, diskPct, crashloop, restarts1h
    };
  }, [raw]);

  const collectionMetric = useMemo(() => {
    if (!raw.collection) return { viewData: [] as ChartData[], loadState: 'error' as const };
    return toMetricSeries(
      { name: 'collection', display_name: '采集状态', description: '', unit: 'none', query: QUERIES.collection.query, color: NEUTRAL_BLUE },
      raw.collection, instanceId, resolvedInstanceName, idValues, instanceIdKeys
    );
  }, [raw.collection, instanceId, resolvedInstanceName, idValues, instanceIdKeys]);
  const collectionStatus = getCollectionStatus(collectionMetric, objectFallbackName);
  const collectionTimeline = buildCollectionStatusTimeline(collectionMetric.loadState, collectionMetric.viewData);

  // 趋势数据
  const trend = useMemo(() => {
    const series = TREND_METRICS.map((m) => {
      const result = raw[m.name];
      const ms = result ? toMetricSeries(m, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys) : { ...m, viewData: [] as ChartData[] };
      return { key: m.name, label: m.display_name, color: m.color, data: ms.viewData };
    });
    const data = mergeChartSeries(series.map((s) => ({ key: s.key, label: s.label, data: s.data })));
    return {
      data,
      metric: buildMetricItem(TREND_METRICS[0]),
      legends: series.map((s) => ({ label: s.label, color: s.color })),
      seriesStyles: series.map((s) => ({ color: s.color }))
    };
  }, [raw, instanceId, resolvedInstanceName, idValues, instanceIdKeys]);

  // 顶部 KPI 卡(带 mini 折线图 + 较上一周期),风格对齐其它监控仪表盘
  const kpiCards = useMemo(() => {
    const series = (name: string, src: any): ChartData[] =>
      src
        ? toMetricSeries(
          { name, display_name: '', description: '', unit: 'none', query: '', color: NEUTRAL_BLUE },
          src, instanceId, resolvedInstanceName, idValues, instanceIdKeys
        ).viewData
        : [];
    const wlSeries = sumSeries([series('deployTotal', raw.deployTotal), series('dsTotal', raw.dsTotal), series('stsTotal', raw.stsTotal)]);
    const prevWl = latestScalar(previousRaw.deployTotal) + latestScalar(previousRaw.dsTotal) + latestScalar(previousRaw.stsTotal);
    return [
      { key: 'nodes', title: '节点总数', desc: '集群节点总数。', value: d.nodesTotal, icon: <CloudServerOutlined />, color: NEUTRAL_BLUE, footer: '集群节点', trendData: series('nodesTotal', raw.nodesTotal), compare: getPeriodCompare(d.nodesTotal, latestScalar(previousRaw.nodesTotal)) },
      { key: 'ns', title: '命名空间', desc: '当前存在 Pod 的命名空间数量(空命名空间不计)。', value: d.namespaces, icon: <AppstoreOutlined />, color: '#13c2c2', footer: '活跃 NS', trendData: series('namespaces', raw.namespaces), compare: getPeriodCompare(d.namespaces, latestScalar(previousRaw.namespaces)) },
      { key: 'pods', title: 'Pod 数量', desc: '集群当前 Pod 总数。', value: d.podsTotal, icon: <DeploymentUnitOutlined />, color: '#9254de', footer: '全部 NS', trendData: series('podsTotal', raw.podsTotal), compare: getPeriodCompare(d.podsTotal, latestScalar(previousRaw.podsTotal)) },
      { key: 'wl', title: '工作负载数量', desc: 'Deployment + StatefulSet + DaemonSet 总数。', value: d.wlTotal, icon: <PartitionOutlined />, color: '#ff8a1f', footer: 'Deploy+STS+DS', trendData: wlSeries, compare: getPeriodCompare(d.wlTotal, prevWl) },
      { key: 'crash', title: '崩溃循环', desc: '当前卡在 CrashLoopBackOff(启动即崩溃、被反复重启)状态的容器个数 —— 是容器数不是重启次数;>0 即有容器起不来。下一步:在「重启 Top Pod」卡或 Pod 列表定位具体 Pod。', value: d.crashloop, icon: <ReloadOutlined />, color: d.crashloop > 0 ? HEALTH_RED : NEUTRAL_INK, footer: '持续重启', trendData: series('crashloop', raw.crashloop), compare: getPeriodCompare(d.crashloop, latestScalar(previousRaw.crashloop)) }
    ];
  }, [d, raw, previousRaw, instanceId, resolvedInstanceName, idValues, instanceIdKeys]);

  // 环图:Pod 状态分布
  const podRing = useMemo(() => {
    const items = [
      { name: 'Running', value: d.running, color: HEALTH_GREEN },
      { name: 'Pending', value: d.pending, color: HEALTH_AMBER },
      { name: 'Failed', value: d.failed, color: HEALTH_RED },
      { name: 'Succeeded', value: d.succeeded, color: RING_DONE }
    ].filter((s) => s.value > 0);
    return {
      data: items.length ? items : [{ name: '无数据', value: 1, color: RING_REST }],
      centerValue: num(d.podsTotal),
      isEmpty: d.podsTotal === 0
    };
  }, [d]);

  // 环图:节点就绪(就绪 vs 未就绪)
  const nodeReadyRing = useMemo(() => {
    const ready = d.nodesReady;
    const notReady = Math.max(d.nodesTotal - ready, 0);
    const items = [
      { name: '就绪', value: ready, color: HEALTH_GREEN },
      { name: '未就绪', value: notReady, color: HEALTH_AMBER }
    ].filter((s) => s.value > 0);
    return {
      data: items.length ? items : [{ name: '无数据', value: 1, color: RING_REST }],
      centerValue: `${num(ready)}/${num(d.nodesTotal)}`,
      isEmpty: d.nodesTotal === 0
    };
  }, [d]);

  // 环图:工作负载可用(可用 vs 副本不全)
  const workloadRing = useMemo(() => {
    const avail = d.wlAvailable;
    const degraded = Math.max(d.wlTotal - avail, 0);
    const items = [
      { name: '可用', value: avail, color: HEALTH_GREEN },
      { name: '副本不全', value: degraded, color: HEALTH_AMBER }
    ].filter((s) => s.value > 0);
    return {
      data: items.length ? items : [{ name: '无数据', value: 1, color: RING_REST }],
      centerValue: `${num(avail)}/${num(d.wlTotal)}`,
      isEmpty: d.wlTotal === 0
    };
  }, [d]);

  // 工作负载可用度条
  const workloadBars = useMemo(() => {
    const mk = (label: string, key: string, color: string) => {
      const v = latestScalar(raw[key]);
      return { label, value: v, display: pct(v), color, max: 100 };
    };
    return [
      mk('Deployment', 'deployPct', NEUTRAL_BLUE),
      mk('StatefulSet', 'stsPct', '#13c2c2'),
      mk('DaemonSet', 'dsPct', '#9254de')
    ];
  }, [raw]);

  // 节点内存 Top-N
  const nodeMemBars = useMemo(() => {
    const rows = seriesLatestByLabel(raw.nodeMemTop, ['node', 'instance_id', 'instance', 'host']).sort((a, b) => b.value - a.value).slice(0, TOP_N);
    return rows.map((r, i) => ({ label: r.label, value: r.value, display: pct(r.value), color: saturationColor(r.value), max: 100, rank: i + 1 }));
  }, [raw.nodeMemTop]);

  // 重启 Top-N Pod
  const restartBars = useMemo(() => {
    const rows = seriesLatestByLabel(raw.restartTop, 'pod').sort((a, b) => b.value - a.value).slice(0, TOP_N);
    const max = rows.length ? Math.max(...rows.map((r) => r.value), 1) : 1;
    return rows.map((r, i) => ({ label: r.label, value: r.value, display: num(r.value), color: r.value > 0 ? HEALTH_RED : HEALTH_GREEN, max, rank: i + 1 }));
  }, [raw.restartTop]);

  // 容量配比堆叠条(已用 / 已请求 / 可分配)
  const capacityRows = useMemo(() => {
    const cpuTotal = latestScalar(raw.cpuAllocatable);
    const memTotal = latestScalar(raw.memAllocatable);
    return [
      {
        label: 'CPU',
        used: latestScalar(raw.cpuUsedCores),
        requested: latestScalar(raw.cpuRequests),
        total: cpuTotal,
        usedDisplay: coresDisplay(latestScalar(raw.cpuUsedCores)),
        requestedDisplay: coresDisplay(latestScalar(raw.cpuRequests)),
        totalDisplay: coresDisplay(cpuTotal)
      },
      {
        label: '内存',
        used: latestScalar(raw.memUsedBytes),
        requested: latestScalar(raw.memRequests),
        total: memTotal,
        usedDisplay: bytesDisplay(latestScalar(raw.memUsedBytes)),
        requestedDisplay: bytesDisplay(latestScalar(raw.memRequests)),
        totalDisplay: bytesDisplay(memTotal)
      }
    ];
  }, [raw.cpuAllocatable, raw.memAllocatable, raw.cpuUsedCores, raw.cpuRequests, raw.memUsedBytes, raw.memRequests]);

  // 资源消耗 Top-N
  const topPodCpuBars = useMemo(() => buildTopBars(raw.topPodCpu, 'pod', '#9254de', coresDisplay), [raw.topPodCpu]);
  const topPodMemBars = useMemo(() => buildTopBars(raw.topPodMem, 'pod', '#13c2c2', bytesDisplay), [raw.topPodMem]);
  const topNsMemBars = useMemo(() => buildTopBars(raw.topNsMem, NS_LABEL, '#13c2c2', bytesDisplay), [raw.topNsMem]);

  // ── 事件 ──
  const onTimeChange = (vals: number[], originValue: number | null) => {
    setTimeValues({ timeRange: vals, originValue: originValue ?? 0 });
  };
  const onInstanceChange = (value: string) => {
    const opt = instanceOptions.find((o) => o.value === value);
    const params = new URLSearchParams(Array.from(searchParams.entries()));
    params.set('instance_id', value);
    params.set('instance_id_values', (opt?.instanceIdValues || [value]).join(','));
    params.set('instance_name', opt?.label || value);
    router.push(`?${params.toString()}`);
  };
  const goBack = () => router.back();

  const guide = (label: string, detail: string) => [{ label, detail }];

  return (
    <div className={styles.page}>
      <div className={styles.shell}>
        <div className={styles.pageHeader}>
          <DashboardPageHeader
            title="K8s 集群监控仪表盘"
            displayMode={displayMode}
            onDisplayModeChange={setDisplayMode}
            timeDefaultValue={timeDefaultValue}
            onTimeChange={onTimeChange}
            onFrequenceChange={setFrequence}
            onRefresh={() => loadAll()}
            onBack={goBack}
            showTimeSelector={false}
            styles={styles}
          />
          <DashboardInstanceCard
            instanceName={resolvedInstanceName}
            metaItems={['VMAgent', 'k8s'].map((item, i) => (
              <span key={i} className={styles.instanceMetaInline}>{item}</span>
            ))}
            icon={<DatabaseOutlined />}
            selectorValue={currentOption?.value || (instanceId ? String(instanceId) : undefined)}
            selectorLoading={instanceLoading}
            selectorOptions={instanceOptions}
            onInstanceChange={onInstanceChange}
            selectorPlaceholder="选择实例"
            selectorTitle={currentOption?.label || resolvedInstanceName}
            isDashboardMode={displayMode === 'dashboard'}
            timeSelectorProps={{ timeDefaultValue, onTimeChange, onFrequenceChange: setFrequence, onRefresh: () => loadAll() }}
            styles={styles}
          />
        </div>

        {/* Tier 1 · 概览:6 张等宽卡(采集状态 + 5 KPI),全 span2(=12) */}
        <div className={styles.sectionLabel}>概览</div>
        <section className={styles.dashboardSection}>
          <div className={styles.sectionGrid}>
            <CollectionStatusCard
              status={collectionStatus}
              timeline={collectionTimeline}
              guideItems={guide('采集状态', '集群监控采集是否正常。')}
              className={styles.span2}
              styles={styles}
            />
            {kpiCards.map((c) => (
              <StatCard
                key={c.key}
                title={<TitleWithGuide title={c.title} items={guide(c.title, c.desc)} styles={styles} />}
                value={num(c.value)}
                unit=""
                icon={c.icon}
                iconStyle={{ color: c.color }}
                color={c.color}
                footer={<span>{c.footer}</span>}
                compare={c.compare}
                trendData={c.trendData}
                noDataType={loading ? 'empty' : undefined}
                className={styles.span2}
                styles={styles}
              />
            ))}
          </div>
        </section>

        {/* Tier 2 · 健康构成:三环统一 span4 */}
        <div className={styles.sectionLabel}>健康构成</div>
        <section className={styles.dashboardSection}>
          <div className={styles.sectionGrid}>
            <RingChartPanel
              title="节点就绪"
              guide={guide('节点就绪', '处于 Ready(可正常调度 Pod)状态的节点数 / 节点总数。有未就绪节点时,到 K8s 节点仪表盘看其资源水位与状态。')}
              data={nodeReadyRing.data}
              centerValue={nodeReadyRing.centerValue}
              centerCaption="节点就绪"
              isEmpty={nodeReadyRing.isEmpty}
              className={styles.span4}
              styles={styles}
            />
            <RingChartPanel
              title="工作负载可用"
              guide={guide('工作负载可用', '全部副本就绪的工作负载数 / 总数;副本不全 = 就绪副本未达期望数量。出现副本不全时,查对应工作负载的 Pod 调度 / 拉镜像 / 崩溃情况。')}
              data={workloadRing.data}
              centerValue={workloadRing.centerValue}
              centerCaption="工作负载可用"
              isEmpty={workloadRing.isEmpty}
              className={styles.span4}
              styles={styles}
            />
            <RingChartPanel
              title="Pod 状态分布"
              guide={guide('Pod 状态分布', 'Running / Pending / Failed / Succeeded 占比。')}
              data={podRing.data}
              centerValue={podRing.centerValue}
              centerCaption="Pod 总数"
              isEmpty={podRing.isEmpty}
              className={styles.span4}
              styles={styles}
            />
          </div>
        </section>

        {/* Tier 3 · 资源水位:趋势(span8)+ 容量配比(span4) */}
        <div className={styles.sectionLabel}>资源水位</div>
        <section className={styles.dashboardSection}>
          <div className={styles.sectionGrid}>
            <TrendChartPanel
              title="资源使用率趋势"
              guide={guide('资源水位趋势', '集群内存、CPU、磁盘使用率随时间变化。')}
              legends={trend.legends}
              data={trend.data}
              metric={trend.metric}
              unit="percent"
              loading={loading}
              seriesStyles={trend.seriesStyles}
              onXRangeChange={undefined}
              className={`${styles.span8} ${styles.compactTrend}`}
              styles={styles}
            />
            <StackedBarPanel
              title="容量配比"
              subtitle="已用 / 已请求 / 可分配"
              guide={guide('容量配比', 'CPU、内存的三个量:已用(实际消耗)、已请求(Pod 预留的 requests)、可分配总量。已请求超过可分配 = 超卖,已用接近总量 = 余量不足。')}
              rows={capacityRows}
              className={styles.span4}
              styles={styles}
            />
          </div>
        </section>

        {/* Tier 4 · 热点排行:Pod 三个维度拆成 3 张独立小卡,其余各占 span4 */}
        <div className={styles.sectionLabel}>热点排行</div>
        <section className={styles.dashboardSection}>
          <div className={styles.sectionGrid}>
            <HorizontalBarPanel
              title="Top Pod · CPU"
              subtitle="核数 · 5m"
              guide={guide('Top Pod · CPU', 'CPU 消耗最高的 Pod。')}
              items={topPodCpuBars}
              tiered
              className={styles.span4}
              styles={styles}
            />
            <HorizontalBarPanel
              title="Top Pod · 内存"
              guide={guide('Top Pod · 内存', '内存占用最高的 Pod。')}
              items={topPodMemBars}
              tiered
              className={styles.span4}
              styles={styles}
            />
            <HorizontalBarPanel
              title="重启 Top Pod"
              subtitle="近 1h"
              guide={guide('重启 Top Pod', '近 1 小时容器重启次数最多的 Pod。')}
              items={restartBars}
              tiered
              className={styles.span4}
              styles={styles}
            />
          </div>
        </section>
        <section className={styles.dashboardSection}>
          <div className={styles.sectionGrid}>
            <HorizontalBarPanel
              title="节点内存 Top"
              guide={guide('节点内存 Top', '内存使用率最高的节点。')}
              items={nodeMemBars}
              tiered
              className={styles.span4}
              styles={styles}
            />
            <HorizontalBarPanel
              title="Top 命名空间 · 内存"
              guide={guide('Top 命名空间 · 内存', '内存占用最高的命名空间。')}
              items={topNsMemBars}
              tiered
              className={styles.span4}
              styles={styles}
            />
            <HorizontalBarPanel
              title="工作负载可用度"
              guide={guide('工作负载可用度', '各类工作负载可用副本占期望副本的比例。')}
              items={workloadBars}
              className={styles.span4}
              styles={styles}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
