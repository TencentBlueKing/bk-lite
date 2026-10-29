'use client';

import type { ReactNode } from 'react';
import {
  ProDashLoading,
  ProInfoHint,
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
import { fragmentationBand } from './architecture-state';
import { REDIS_PALETTE } from '../config';
import styles from '../index.module.scss';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import {
  redisChartPoints,
  redisDisplay,
  redisLatest,
  redisMemoryLimitUnset,
  redisProductText,
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
const hintClass = 'm-0 text-[12px] leading-5 text-[var(--color-text-3)]';

const TONE_COLOR = {
  ok: 'var(--color-success)',
  near: 'var(--color-warning)',
  full: 'var(--color-fail)',
  neutral: 'var(--color-text-3)'
} as const;

type PressureTone = 'ok' | 'near' | 'full';

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

function HintCopy({ lines, kind }: { lines: readonly string[]; kind: string }) {
  return (
    <ProInfoHint
      kind={kind}
      label={lines.join(' ')}
      content={(
        <div className="max-w-[380px] text-[13px] font-normal leading-[1.55] text-[var(--color-text-2)]">
          {lines.map((line) => (
            <p key={line} className="m-0 [&+&]:mt-2">{line}</p>
          ))}
        </div>
      )}
    />
  );
}

function Spark({
  metricMap,
  name,
  label,
  color,
  unit,
  keepSeriesWhenWindowEmpty = false,
  fill = false
}: {
  metricMap: RedisMetricMap;
  name: string;
  label: string;
  color: string;
  unit: MetricUnit;
  keepSeriesWhenWindowEmpty?: boolean;
  /** 折线吃满所在卡片剩余高度。重点关注 spark 不要开。 */
  fill?: boolean;
}) {
  const text = useRedisText();
  const proTime = useProTimeWindow();
  const plotted = redisChartPoints(
    metricMap,
    [{ name, label }],
    proTime?.window ?? null,
    keepSeriesWhenWindowEmpty
  );
  return (
    <ThinTimeSeries
      bare
      numericAxis
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

function pressureTone(percent: number): PressureTone {
  if (percent >= 95) return 'full';
  if (percent >= 80) return 'near';
  return 'ok';
}

/** 五档色阶，档与档之间留缝，避免画成磁盘进度条。 */
function PressureScale({ percent }: { percent: number }) {
  const tone = pressureTone(percent);
  const active = Math.min(4, Math.floor(percent >= 100 ? 4 : percent / 20));
  return (
    <div className="flex items-end gap-1.5" role="img" aria-label={tone}>
      {Array.from({ length: 5 }, (_, index) => {
        const on = index <= active;
        const color = on ? TONE_COLOR[tone] : 'var(--color-fill-2)';
        return (
          <span
            key={index}
            className={`flex-1 rounded-sm ${index === active ? 'h-3' : 'h-2'}`}
            style={{ background: color }}
          />
        );
      })}
    </div>
  );
}

function BigNumber({
  title,
  metric,
  unit,
  unitLabel,
  color,
  reading,
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
  reading?: string;
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
        <>
          <div className={valueClass} style={{ color: valueColor }}>{headline}</div>
          {reading ? (
            <p className="m-0 text-[13px] font-medium leading-5" style={{ color: valueColor }}>{reading}</p>
          ) : null}
        </>
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
    : state === 'tight'
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
          <HintCopy
            kind="redis-capacity"
            lines={[
              text('capacityBandOk'),
              text('capacityBandTight'),
              text('capacityBandUnset'),
              text('capacityPctUsed'),
              text('capacityPctNotRemain')
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
          <p className="m-0 text-[12px] leading-5 text-[var(--color-text-2)]">{text('memoryLimitUnsetTip')}</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-baseline gap-2">
            <span className="text-[14px] font-semibold" style={{ color: stateColor }}>{stateLabel}</span>
            {percent != null ? (
              <span className="tabular-nums text-[13px] text-[var(--color-text-2)]">{`${percent.toFixed(1)}%`}</span>
            ) : null}
          </div>
          <p className="m-0 text-[13px] tabular-nums text-[var(--color-text-1)]">
            {text('seriesUsed')} {reading(metricMap, 'redis_used_memory', 'bytes')}
            {` / ${text('seriesLimit')} ${reading(metricMap, 'redis_maxmemory', 'bytes')}`}
          </p>
          {percent != null ? <PressureScale percent={percent} /> : null}
          <p className={hintClass}>{text('capacityHint')}</p>
        </div>
      )}
    </section>
  );
}

function FragBands({ active }: { active: 'low' | 'ok' | 'high' | null }) {
  const text = useRedisText();
  // 展示区间与 fragmentationBand 一致：< 1 偏低，1–1.5 常见，> 1.5 偏高。阈值不在这里改。
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

const FRAG_READING = {
  low: 'fragReadLow',
  ok: 'fragReadOk',
  high: 'fragReadHigh'
} as const satisfies Record<'low' | 'ok' | 'high', RedisCategoryCopyKey>;

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
            reading={band ? text(FRAG_READING[band]) : undefined}
            extra={<FragBands active={band} />}
            hint={<HintCopy kind="redis-frag" lines={[text('fragIdeal')]} />}
            metricMap={metricMap}
            pending={pending}
          />
        </div>
      </ProSection>
      <ProSection title={text('sectionLifecycle')}>
        <div data-redis-feature="lifecycle">
          <RedisTrendChart spec={lifecycleTrend} metricMap={metricMap} pending={pending} />
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
  const hits = redisDisplay(metricMap, 'redis_keyspace_hits_rate', 'cps');
  const misses = redisDisplay(metricMap, 'redis_keyspace_misses_rate', 'cps');
  const hitRate = redisLatest(metricMap, 'redis_keyspace_hitrate');
  const loading = (pending.has('redis_keyspace_hits_rate') || pending.has('redis_keyspace_misses_rate'))
    && hits.value == null && misses.value == null;
  const bothKnown = hits.value != null && misses.value != null;
  const empty = !loading && !bothKnown;
  const total = Math.max(hits.value ?? 0, 0) + Math.max(misses.value ?? 0, 0);
  const centerValue = bothKnown
    ? (total > 0 ? `${((Math.max(misses.value ?? 0, 0) / total) * 100).toFixed(1)}%` : '0.0%')
    : '';
  const penetrating = bothKnown && (misses.value ?? 0) > (hits.value ?? 0) && (misses.value ?? 0) > 0;
  const hitLow = hitRate != null && (hitRate < 90 || penetrating);
  const rateLabel = (name: string) => (
    redisProductText(metricMap, name, 'cps', text('rateUnit')) ?? text('legendQuiet')
  );
  const centerCaption = (
    <span data-redis-center="penetration" className="inline-flex items-center gap-1">
      {text('penetration')}
      <HintCopy
        kind="redis-penetration"
        lines={[text('penetrationFormula'), text('penetrationReach'), text('penetrationLook')]}
      />
    </span>
  );
  return (
    <Pane pane="cache">
      <ProSection title={text('sectionCache')}>
        <div className="grid min-w-0 grid-cols-1 items-stretch gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className="flex h-full min-w-0 flex-col gap-3">
            {loading ? (
              <section className={`${styles.panel} h-full`} data-redis-feature="hit-ring">
                <FeatureHead title={text('cardHitVsMiss')} />
                <ProDashLoading />
              </section>
            ) : (
              <div data-redis-feature="hit-ring" className="min-w-0">
                <RingChartPanel
                  className="h-full"
                  title={text('cardHitVsMiss')}
                  data={[
                    { name: text('seriesHit'), value: Math.max(hits.value ?? 0, 0), color: REDIS_PALETTE.emerald, display: rateLabel('redis_keyspace_hits_rate') },
                    { name: text('seriesMiss'), value: Math.max(misses.value ?? 0, 0), color: REDIS_PALETTE.rose, display: rateLabel('redis_keyspace_misses_rate') }
                  ]}
                  infoRows={[
                    { name: text('seriesHit'), color: REDIS_PALETTE.emerald, primary: rateLabel('redis_keyspace_hits_rate') },
                    { name: text('seriesMiss'), color: REDIS_PALETTE.rose, primary: rateLabel('redis_keyspace_misses_rate') }
                  ]}
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
          <section className={`${styles.panel} h-full`} data-redis-feature="hit-rate">
            <FeatureHead
              title={text('cardHitRate')}
              hint={(
                <HintCopy
                  kind="redis-hit-rate"
                  lines={[text('hitRateHint'), text('hitRateSteady')]}
                />
              )}
            />
            {pending.has('redis_keyspace_hitrate') && hitRate == null ? (
              <ProDashLoading />
            ) : hitRate == null ? (
              <EmptySample />
            ) : (
              <div className="flex min-h-[168px] min-w-0 flex-1 flex-col" data-redis-spark="hit-rate">
                <Spark
                  fill
                  metricMap={metricMap}
                  name="redis_keyspace_hitrate"
                  label={text('cardHitRate')}
                  color={hitLow ? REDIS_PALETTE.amber : REDIS_PALETTE.emerald}
                  unit="percent"
                />
              </div>
            )}
          </section>
        </div>
      </ProSection>
      <ProSection title={text('sectionTrends')}>
        <RedisTrendChart spec={hitTrend} metricMap={metricMap} pending={pending} />
      </ProSection>
    </Pane>
  );
}

export function ClientsPane({
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
  const rejectValue = redisLatest(metricMap, 'redis_rejected_connections_rate');
  const rejectHint = rejectValue == null
    ? undefined
    : rejectValue > 0
      ? text('rejectedHot')
      : text('rejectedCalm');
  return (
    <Pane pane="clients">
      <ProSection title={text('sectionBlocked')}>
        <div
          data-redis-feature="blocked"
          data-redis-blocked={blockedLoading ? 'loading' : blocked == null ? 'quiet' : warn ? 'warn' : 'healthy'}
          data-redis-spark="blocked"
        >
          <RedisTrendChart spec={blockedTrend} metricMap={metricMap} pending={pending} />
        </div>
      </ProSection>
      <ProSection title={text('sectionConnections')}>
        <div className={featureGrid}>
          <div data-redis-feature="clients">
            <RedisTrendChart spec={clientsTrend} metricMap={metricMap} pending={pending} />
          </div>
          <div data-redis-feature="rejected">
            <RedisTrendChart
              spec={rejectedTrend}
              metricMap={metricMap}
              pending={pending}
              hint={rejectHint}
            />
          </div>
        </div>
      </ProSection>
    </Pane>
  );
}

export function ThroughputPane({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  return (
    <Pane pane="throughput">
      <ProSection title={text('sectionTrends')}>
        <div className={featureGrid}>
          <RedisTrendChart spec={opsTrend} metricMap={metricMap} pending={pending} />
          <div data-redis-network="trend">
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
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <RedisTrendChart spec={commandTrend} metricMap={metricMap} pending={pending} />
      <RedisTrendChart spec={hitTrend} metricMap={metricMap} pending={pending} />
    </div>
  );
}
