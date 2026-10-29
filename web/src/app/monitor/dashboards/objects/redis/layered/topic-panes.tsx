'use client';

import type { ReactNode } from 'react';
import type { ChartData } from '@/app/monitor/types';
import {
  ProDashLoading,
  ProSection,
  ThinTimeSeries,
  proChromeClass
} from '../../host/layered/pro-chrome';
import chart from '../../host/layered/layered.module.scss';
import { formatFocusUnitText } from '../../host/layered/focus-axis';
import { useProTimeWindow } from '../../host/layered/pro-time-window';
import { RingChartPanel } from '../../../shared/widgets';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import type { MetricUnit } from '../../../shared/types';
import { fragmentationBand, PRESSURE_COLOR, pressureTone, type PressureTone } from './architecture-state';
import { REDIS_PALETTE } from '../config';
import styles from '../index.module.scss';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import { RedisHint } from './redis-hint';
import {
  redisChartPoints,
  redisDisplay,
  redisLatest,
  redisMemoryLimitUnset,
  redisProductText,
  redisShownHitPercent,
  scaleHitRateChart,
  type RedisMetricMap
} from './series';
import RedisTrendChart, { type RedisTrendSpec } from './trend-chart';

const commandTrend: RedisTrendSpec = {
  titleKey: 'chartCommand',
  unit: 'cps',
  series: [
    { name: 'redis_total_commands_processed_rate', labelKey: 'seriesCommands', color: REDIS_PALETTE.cyan }
  ]
};

const hitTrend: RedisTrendSpec = {
  titleKey: 'chartHit',
  unit: 'cps',
  series: [
    { name: 'redis_keyspace_hits_rate', labelKey: 'seriesHit', color: REDIS_PALETTE.emerald },
    { name: 'redis_keyspace_misses_rate', labelKey: 'seriesMiss', color: REDIS_PALETTE.rose }
  ]
};

const lifecycleTrend: RedisTrendSpec = {
  titleKey: 'chartLifecycleTrend',
  unit: 'cps',
  series: [
    { name: 'redis_expired_keys_rate', labelKey: 'seriesExpired', color: REDIS_PALETTE.indigo },
    { name: 'redis_evicted_keys_rate', labelKey: 'seriesEvicted', color: REDIS_PALETTE.rose }
  ]
};

const clientsTrend: RedisTrendSpec = {
  titleKey: 'seriesClients',
  hintKey: 'clientsReading',
  unit: 'counts',
  series: [
    { name: 'redis_clients', labelKey: 'seriesClients', color: REDIS_PALETTE.blue }
  ]
};

const rejectedTrend: RedisTrendSpec = {
  titleKey: 'cardRejected',
  hintKey: 'rejectedDefine',
  unit: 'cps',
  series: [
    { name: 'redis_rejected_connections_rate', labelKey: 'seriesRejected', color: REDIS_PALETTE.rose }
  ]
};

const blockedTrend: RedisTrendSpec = {
  titleKey: 'cardBlocked',
  hintKey: 'blockedHint',
  unit: 'counts',
  series: [
    { name: 'redis_blocked_clients', labelKey: 'seriesBlocked', color: REDIS_PALETTE.orange }
  ]
};

const opsTrend: RedisTrendSpec = {
  titleKey: 'chartOps',
  unit: 'cps',
  series: [
    { name: 'redis_instantaneous_ops_per_sec', labelKey: 'seriesOps', color: REDIS_PALETTE.blue },
    { name: 'redis_total_commands_processed_rate', labelKey: 'seriesCommands', color: REDIS_PALETTE.cyan }
  ]
};

const netTrend: RedisTrendSpec = {
  titleKey: 'chartNetTrend',
  unit: 'byteps',
  series: [
    { name: 'redis_total_net_input_bytes_rate', labelKey: 'seriesNetIn', color: REDIS_PALETTE.blue },
    { name: 'redis_total_net_output_bytes_rate', labelKey: 'seriesNetOut', color: REDIS_PALETTE.emerald }
  ]
};

/** 连接三卡与吞吐两卡跟主机图格同宽。阻塞不再单独占满一行。 */
const connectionGrid = `${chart.chartGrid3} items-stretch [&>*]:min-w-0 [&>*]:h-full [&_section]:h-full`;
const throughputGrid = `${chart.chartGrid2} items-stretch [&>*]:min-w-0 [&>*]:h-full [&_section]:h-full`;
/** 百分比折线钉 0–100，图表库不能再把 94 抬成 120。 */
const PERCENT_VALUE_BOUNDS = { min: 0, max: 100 };

/**
 * 环图壳仍写 panelTitle 槽。CSS Module 导出不是可枚举普通对象，展开会丢掉
 * panel / ring 类，所以只按键改挂 chartTitle，其余壳层原样走。
 */
const ringStyles = new Proxy(styles, {
  get(target, key) {
    if (key === 'panelHeading') return chart.chartHead;
    if (key === 'panelTitle') return `${chart.chartTitle} m-0`;
    return Reflect.get(target, key);
  }
});

const featureGrid = 'grid min-w-0 grid-cols-1 items-stretch gap-3 lg:grid-cols-2';
/** 穿透环约 1/4，命中率折线吃剩余 3/4。窄屏跟主机图格一样在 1100 以下叠成一列。 */
const cacheRowGrid = 'grid min-w-0 grid-cols-1 items-stretch gap-3 min-[1100px]:grid-cols-[minmax(0,1fr)_minmax(0,3fr)] [&>*]:min-w-0 [&>*]:h-full [&_section]:h-full';

const TONE_COLOR = {
  ...PRESSURE_COLOR,
  neutral: 'var(--color-text-3)'
} as const;

function useRedisText() {
  const { t } = useDashboardText();
  return (key: RedisCategoryCopyKey) => redisCategoryText(t, key);
}

/** 与 ThinTimeSeries 卡头同构：chartHead + chartTitle（13px/600）。说明挂在问号上。 */
function FeatureHead({ title, hint, unit }: { title: string; hint?: ReactNode; unit?: string }) {
  const unitText = formatFocusUnitText(unit);
  const marked = Boolean(hint || unitText);
  return (
    <div className={chart.chartHead}>
      <div className={chart.chartTitleGroup}>
        <div className={chart.chartTitleBlock}>
          <div className={chart.chartTitle}>
            {marked ? (
              <span className="inline-flex items-center gap-1">
                {title}
                {hint}
                {unitText ? <span className={chart.shortcutAxisUnit}>{unitText}</span> : null}
              </span>
            ) : title}
          </div>
        </div>
      </div>
    </div>
  );
}

function Spark({
  metricMap,
  name,
  label,
  color,
  unit,
  keepSeriesWhenWindowEmpty = false,
  fill = false,
  data
}: {
  metricMap: RedisMetricMap;
  name: string;
  label: string;
  color: string;
  unit: MetricUnit;
  keepSeriesWhenWindowEmpty?: boolean;
  /** 折线吃满所在卡片剩余高度。重点关注 spark 不要开。 */
  fill?: boolean;
  /** 已经换算好的点。传入后不再按指标名二次缩放。 */
  data?: ChartData[];
}) {
  const text = useRedisText();
  const proTime = useProTimeWindow();
  const plottedRaw = data ?? redisChartPoints(
    metricMap,
    [{ name, label }],
    proTime?.window ?? null,
    keepSeriesWhenWindowEmpty
  );
  const plotted = data ? plottedRaw : (name === 'redis_keyspace_hitrate' ? scaleHitRateChart(plottedRaw) : plottedRaw);
  return (
    <ThinTimeSeries
      bare
      numericAxis
      valueBounds={unit === 'percent' || unit === 'percentunit' ? PERCENT_VALUE_BOUNDS : undefined}
      className={[proChromeClass.focusChart, fill ? chart.focusChartFill : ''].filter(Boolean).join(' ')}
      title=""
      unit={unit}
      emptyText={text('sampleEmpty')}
      data={plotted}
      legends={[{ label, color }]}
    />
  );
}

function EmptySample({ hint }: { hint?: string }) {
  const text = useRedisText();
  return (
    <div className="flex flex-col gap-1" data-redis-empty="sample">
      <div className="text-[15px] font-semibold leading-6 text-[var(--color-text-1)]">{text('sampleEmpty')}</div>
      {hint ? <p className="m-0 text-[12px] leading-5 text-[var(--color-text-2)]">{hint}</p> : null}
    </div>
  );
}

function Pane({ pane, children }: { pane: string; children: ReactNode }) {
  return (
    <div data-redis-pane={pane} className="contents">
      {children}
    </div>
  );
}

/** 容量压力底条。按已用占比填充，颜色跟当前档。没有占比时不画，避免用 0 假满。 */
function CapacityMeter({ percent, tone }: { percent: number; tone: PressureTone }) {
  const clamped = Math.min(100, Math.max(0, percent));
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-fill-2)]"
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Number(clamped.toFixed(1))}
      data-redis-capacity-meter={tone}
    >
      <span
        className="block h-full rounded-full"
        style={{ width: `${clamped}%`, background: TONE_COLOR[tone] }}
      />
    </div>
  );
}

function BigNumber({
  title,
  metric,
  unit,
  unitLabel,
  color,
  extra,
  emphasis = 'normal',
  feature,
  metricMap,
  pending,
  hint,
  emptyHint,
  spark,
  keepSeriesWhenWindowEmpty
}: {
  title: string;
  metric: string;
  unit: MetricUnit;
  unitLabel?: string;
  color: string;
  extra?: ReactNode;
  emphasis?: 'hero' | 'normal';
  feature: string;
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
  hint?: ReactNode;
  emptyHint?: string;
  spark?: boolean;
  keepSeriesWhenWindowEmpty?: boolean;
}) {
  const shown = redisDisplay(metricMap, metric, unit);
  const loading = pending.has(metric) && shown.value == null;
  const valueColor = shown.value == null ? 'var(--color-text-3)' : color;
  const headline = shown.value == null
    ? ''
    : unit === 'none'
      ? shown.value.toFixed(2)
      : redisProductText(metricMap, metric, unit, unitLabel) ?? '';
  const valueClass = emphasis === 'hero'
    ? 'flex items-baseline gap-2 text-[32px] font-bold leading-none tracking-tight tabular-nums sm:text-[40px]'
    : styles.statValue;
  const body = loading ? (
    <ProDashLoading />
  ) : (
    <div className="flex flex-col gap-2">
      {shown.value == null ? (
        <EmptySample hint={emptyHint} />
      ) : (
        <div className={valueClass} style={{ color: valueColor }}>{headline}</div>
      )}
      {extra}
    </div>
  );
  return (
    <section
      className={`${styles.panel} h-full${emphasis === 'hero' ? ' !border-l-4 !border-l-[var(--color-primary)]' : ''}`}
      data-redis-feature={feature}
      data-redis-emphasis={emphasis}
      data-redis-state={loading ? 'loading' : shown.value == null ? 'empty' : 'value'}
    >
      <FeatureHead title={title} hint={hint} unit={unit === 'none' ? unitLabel : undefined} />
      {spark ? (
        <div className="flex items-stretch gap-3">
          <div className="flex min-w-0 flex-1 flex-col justify-center">{body}</div>
          <div className="min-w-0 flex-1" data-redis-spark={feature}>
            <Spark
              metricMap={metricMap}
              name={metric}
              label={title}
              color={color}
              unit={unit}
              keepSeriesWhenWindowEmpty={keepSeriesWhenWindowEmpty}
            />
          </div>
        </div>
      ) : body}
    </section>
  );
}

function reading(metricMap: RedisMetricMap, name: string, unit: MetricUnit) {
  const shown = redisDisplay(metricMap, name, unit);
  if (shown.value == null) return '';
  return shown.unit ? `${shown.text}${shown.unit}` : shown.text;
}

function CapacityCard({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const unset = redisMemoryLimitUnset(metricMap);
  const used = redisDisplay(metricMap, 'redis_used_memory', 'bytes');
  const limit = redisDisplay(metricMap, 'redis_maxmemory', 'bytes');
  const waiting = !unset && (
    (pending.has('redis_used_memory') && used.value == null)
    || (pending.has('redis_maxmemory') && limit.value == null)
  );
  const percent = !unset && limit.value != null && limit.value > 0 && used.value != null
    ? Math.min(100, Math.max(0, (used.value / limit.value) * 100))
    : null;
  const tone: PressureTone | 'neutral' = unset || percent == null ? 'neutral' : pressureTone(percent);
  const state = unset ? 'unset' : percent == null ? 'quiet' : tone === 'ok' ? 'ok' : 'tight';
  const stateLabel = state === 'unset'
    ? text('capacityUnset')
    : tone === 'full'
      ? text('capacityFull')
      : tone === 'near'
        ? text('capacityTight')
        : text('capacityOk');
  const stateColor = state === 'tight' ? TONE_COLOR[tone === 'neutral' ? 'near' : tone] : state === 'ok' ? TONE_COLOR.ok : TONE_COLOR.neutral;
  return (
    <section
      className={`${styles.panel} h-full`}
      data-redis-feature="capacity"
      data-redis-capacity={waiting ? 'loading' : state}
      data-redis-pressure={percent == null ? undefined : pressureTone(percent)}
    >
      <FeatureHead
        title={text('cardCapacity')}
        hint={(
          <RedisHint
            kind="redis-capacity"
            groups={[
              {
                title: text('capacityRatioTitle'),
                lines: [text('capacityPctUsed'), text('capacityPctNotRemain')]
              },
              { title: text('capacityBandTitle') },
              { title: text('capacityOk'), lines: [text('capacityBandOk')] },
              { title: text('capacityTight'), lines: [text('capacityBandTight')] },
              { title: text('capacityFull'), lines: [text('capacityBandFull')] },
              { title: text('capacityUnset'), lines: [text('capacityBandUnset')] }
            ]}
          />
        )}
      />
      {waiting ? (
        <ProDashLoading />
      ) : state === 'quiet' ? (
        <EmptySample />
      ) : state === 'unset' ? (
        <div className="flex flex-col gap-3" data-redis-bar="hidden">
          <div className="text-[28px] font-bold leading-none tabular-nums text-[var(--color-text-1)]">
            {used.value == null ? text('sampleEmpty') : reading(metricMap, 'redis_used_memory', 'bytes')}
          </div>
          <div className="text-[15px] font-semibold leading-6 text-[var(--color-text-1)]">{text('memoryLimitUnset')}</div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline gap-x-1.5">
            <span className="text-[14px] font-semibold" style={{ color: stateColor }}>{stateLabel}</span>
            {percent != null ? (
              <span className="tabular-nums text-[13px] text-[var(--color-text-2)]">
                {`· ${text('capacityUsedOf')} ${percent.toFixed(1)}%`}
              </span>
            ) : null}
          </div>
          <p className="m-0 text-[13px] tabular-nums text-[var(--color-text-1)]">
            {text('seriesUsed')} {reading(metricMap, 'redis_used_memory', 'bytes')}
            {` / ${text('seriesLimit')} ${reading(metricMap, 'redis_maxmemory', 'bytes')}`}
          </p>
          {percent != null && tone !== 'neutral' ? (
            <CapacityMeter percent={percent} tone={tone} />
          ) : null}
        </div>
      )}
    </section>
  );
}

function FragBands({ active }: { active: 'low' | 'ok' | 'high' | null }) {
  const text = useRedisText();
  // 展示区间与 fragmentationBand 一致：< 1 偏低，1–1.5 适中，> 1.5 偏高。阈值不在这里改。
  const items = [
    { key: 'low' as const, label: text('fragLow'), range: '< 1.0', color: TONE_COLOR.near },
    { key: 'ok' as const, label: text('fragOk'), range: '1.0 – 1.5', color: TONE_COLOR.ok },
    { key: 'high' as const, label: text('fragHigh'), range: '> 1.5', color: TONE_COLOR.full }
  ];
  return (
    <div className="flex gap-1.5" data-redis-frag={active ?? 'quiet'}>
      {items.map((item) => {
        const on = item.key === active;
        return (
          <span
            key={item.key}
            className="inline-flex min-h-6 flex-1 flex-col items-center justify-center gap-0.5 rounded-md px-1 py-1 text-center leading-4"
            style={{
              color: on ? item.color : 'var(--color-text-3)',
              background: on ? `color-mix(in srgb, ${item.color} 14%, var(--color-bg))` : 'var(--color-fill-2)',
              fontWeight: on ? 600 : 400
            }}
          >
            <span className="text-[12px]">{item.label}</span>
            <span className="text-[11px] tabular-nums">{item.range}</span>
          </span>
        );
      })}
    </div>
  );
}

export function MemoryPane({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const frag = redisLatest(metricMap, 'redis_mem_fragmentation_ratio');
  const band = fragmentationBand(frag);
  const fragColor = band == null
    ? 'var(--color-text-3)'
    : band === 'high'
      ? TONE_COLOR.full
      : band === 'low'
        ? TONE_COLOR.near
        : TONE_COLOR.ok;
  return (
    <Pane pane="memory">
      <ProSection title={text('sectionCapacity')}>
        <div className={featureGrid}>
          <CapacityCard metricMap={metricMap} pending={pending} />
          <BigNumber
            feature="frag"
            title={text('focusFrag')}
            metric="redis_mem_fragmentation_ratio"
            unit="none"
            unitLabel={text('fragTimes')}
            color={fragColor}
            extra={<FragBands active={band} />}
            hint={(
              <RedisHint
                kind="redis-frag"
                groups={[
                  { lines: [text('fragIdeal')] },
                  { title: text('fragLow'), lines: [text('fragIdealLow')] },
                  { title: text('fragOk'), lines: [text('fragIdealMid')] },
                  { title: text('fragHigh'), lines: [text('fragIdealHigh')] }
                ]}
              />
            )}
            metricMap={metricMap}
            pending={pending}
          />
        </div>
      </ProSection>
    </Pane>
  );
}

export function MemoryCacheTrendPane({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const limitOn = (redisLatest(metricMap, 'redis_maxmemory') ?? 0) > 0;
  const memoryTrend: RedisTrendSpec = {
    titleKey: 'chartMemory',
    unit: 'bytes',
    series: [
      { name: 'redis_used_memory', labelKey: 'seriesUsed', color: REDIS_PALETTE.blue },
      ...(limitOn ? [{
        name: 'redis_maxmemory',
        labelKey: 'seriesLimit' as const,
        color: REDIS_PALETTE.neutral,
        dashed: true
      }] : [])
    ]
  };
  const memoryLines = [
    text('memoryPressureUsed'),
    text('memoryPressureLimit'),
    text('memoryPressureOmit'),
    text('memoryPressureClose')
  ];
  return (
    <Pane pane="memory-cache-trends">
      <ProSection title={text('sectionTrends')}>
        <div className={connectionGrid} data-redis-trends="memory-cache">
          <div className="min-w-0 h-full" data-redis-feature="memory-pressure" data-redis-limit={limitOn ? 'on' : 'off'}>
            <RedisTrendChart
              spec={memoryTrend}
              metricMap={metricMap}
              pending={pending}
              hint={<RedisHint kind="redis-memory-pressure" lines={memoryLines} />}
            />
          </div>
          <div className="min-w-0 h-full" data-redis-feature="lifecycle">
            <RedisTrendChart spec={lifecycleTrend} metricMap={metricMap} pending={pending} />
          </div>
          <div className="min-w-0 h-full" data-redis-trend="hit">
            <RedisTrendChart spec={hitTrend} metricMap={metricMap} pending={pending} />
          </div>
        </div>
      </ProSection>
    </Pane>
  );
}

export function CachePane({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const proTime = useProTimeWindow();
  const hits = redisDisplay(metricMap, 'redis_keyspace_hits_rate', 'cps');
  const misses = redisDisplay(metricMap, 'redis_keyspace_misses_rate', 'cps');
  const windowSettled = !pending.has('redis_keyspace_hits_rate') && !pending.has('redis_keyspace_misses_rate');
  const shown = redisShownHitPercent(metricMap, proTime?.window ?? null, windowSettled);
  const keyspace = shown.keyspace;
  const hitRate = shown.percent;
  const usingFallback = shown.fallback;
  const loading = !windowSettled && hitRate == null && !keyspace.bothKnown;
  const bothKnown = keyspace.bothKnown;
  const rateKnown = keyspace.penetrationPercent != null;
  const empty = !loading && !bothKnown;
  const centerValue = rateKnown
    ? `${keyspace.penetrationPercent?.toFixed(1)}%`
    : (bothKnown ? '--' : '');
  const penetrating = bothKnown && keyspace.hitPercent != null && keyspace.hitPercent < 50;
  const hitLow = hitRate != null && (hitRate < 90 || penetrating);
  const centerCaption = (
    <span data-redis-center="penetration" data-redis-penetration={rateKnown ? 'value' : bothKnown ? 'zero' : 'quiet'} className="inline-flex items-center gap-1">
      {text('penetration')}
      <RedisHint
        kind="redis-penetration"
        lines={[text('penetrationFormula'), text('penetrationLook')]}
      />
    </span>
  );
  return (
    <Pane pane="cache">
      <ProSection title={text('sectionCache')}>
        <div className={cacheRowGrid} data-redis-cache-row="quarter">
          <div className="min-w-0 h-full">
            {loading ? (
              <section className={`${styles.panel} h-full w-full`} data-redis-feature="hit-ring">
                <FeatureHead title={text('penetration')} />
                <ProDashLoading />
              </section>
            ) : (
              <div data-redis-feature="hit-ring" className="h-full min-w-0">
                <RingChartPanel
                  className="h-full w-full"
                  title={text('penetration')}
                  data={[
                    { name: text('seriesHit'), value: Math.max(hits.value ?? 0, 0), color: REDIS_PALETTE.emerald },
                    { name: text('seriesMiss'), value: Math.max(misses.value ?? 0, 0), color: REDIS_PALETTE.rose }
                  ]}
                  showInfo={false}
                  centerValue={centerValue}
                  centerCaption={centerCaption}
                  isEmpty={empty}
                  emptyDescription={text('cacheRingEmpty')}
                  ringCardClassName={styles.cacheHitRing}
                  styles={ringStyles}
                />
              </div>
            )}
          </div>
          <section className={`${styles.panel} h-full min-w-0`} data-redis-feature="hit-rate">
            <FeatureHead
              title={text('cardHitRate')}
              hint={(
                <RedisHint
                  kind="redis-hit-rate"
                  lines={[
                    text('hitRateHint'),
                    text('hitRateSteady'),
                    text('hitRateFallback')
                  ]}
                />
              )}
            />
            {loading ? (
              <ProDashLoading />
            ) : hitRate == null ? (
              <EmptySample />
            ) : (
              <div
                className="flex min-h-[168px] min-w-0 flex-1 flex-col"
                data-redis-spark="hit-rate"
                data-redis-hit-source={usingFallback ? 'lifetime' : 'window'}
              >
                <Spark
                  fill
                  metricMap={metricMap}
                  name="redis_keyspace_hitrate"
                  label={text('cardHitRate')}
                  color={hitLow ? REDIS_PALETTE.amber : REDIS_PALETTE.emerald}
                  unit="percent"
                  data={usingFallback
                    ? scaleHitRateChart(redisChartPoints(
                      metricMap,
                      [{ name: 'redis_keyspace_hitrate', label: text('cardHitRate') }],
                      proTime?.window ?? null
                    ))
                    : keyspace.points}
                />
              </div>
            )}
          </section>
        </div>
      </ProSection>
    </Pane>
  );
}

export function ConnThroughputPane({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const blocked = redisLatest(metricMap, 'redis_blocked_clients');
  const blockedLoading = pending.has('redis_blocked_clients') && blocked == null;
  const warn = blocked != null && blocked > 0;
  return (
    <Pane pane="conn-throughput">
      <ProSection title={text('sectionConnections')}>
        <div className={connectionGrid}>
          <div
            className="min-w-0 h-full"
            data-redis-feature="blocked"
            data-redis-blocked={blockedLoading ? 'loading' : blocked == null ? 'quiet' : warn ? 'warn' : 'healthy'}
          >
            <RedisTrendChart spec={blockedTrend} metricMap={metricMap} pending={pending} />
          </div>
          <div className="min-w-0 h-full" data-redis-feature="clients">
            <RedisTrendChart spec={clientsTrend} metricMap={metricMap} pending={pending} />
          </div>
          <div className="min-w-0 h-full" data-redis-feature="rejected">
            <RedisTrendChart spec={rejectedTrend} metricMap={metricMap} pending={pending} />
          </div>
        </div>
      </ProSection>
      <ProSection title={text('sectionThroughput')}>
        <div className={throughputGrid} data-redis-trends="conn">
          <div className="min-w-0 h-full" data-redis-trend="ops">
            <RedisTrendChart spec={opsTrend} metricMap={metricMap} pending={pending} />
          </div>
          <div className="min-w-0 h-full" data-redis-network="trend">
            <RedisTrendChart spec={netTrend} metricMap={metricMap} pending={pending} />
          </div>
        </div>
      </ProSection>
    </Pane>
  );
}

export function CompactTrends({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  return (
    <div className={throughputGrid} data-redis-trends="overview">
      <div className="min-w-0 h-full" data-redis-trend="command">
        <RedisTrendChart spec={commandTrend} metricMap={metricMap} pending={pending} />
      </div>
      <div className="min-w-0 h-full" data-redis-trend="network">
        <RedisTrendChart spec={netTrend} metricMap={metricMap} pending={pending} />
      </div>
    </div>
  );
}
