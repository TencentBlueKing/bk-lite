'use client';

import type { ReactNode } from 'react';
import { Progress } from 'antd';
import { ProDashLoading, ProSection } from '../../host/layered/pro-chrome';
import chart from '../../host/layered/layered.module.scss';
import { RingChartPanel } from '../../../shared/widgets';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import type { MetricUnit } from '../../../shared/types';
import { REDIS_PALETTE } from '../config';
import styles from '../index.module.scss';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import {
  redisDisplay,
  redisLatest,
  redisMemoryLimitUnset,
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

const rejectTrend: RedisTrendSpec = {
  titleKey: 'chartRejected',
  unit: 'cps',
  series: [
    { name: 'redis_rejected_connections_rate', labelKey: 'seriesRejected', color: REDIS_PALETTE.rose }
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
const quietClass = 'm-0 text-[13px] text-[var(--color-text-3)]';

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

/** 与 ThinTimeSeries 卡头同构：chartHead + chartTitle（13px/600）。加载和空态也留着。 */
function FeatureHead({ title }: { title: string }) {
  return (
    <div className={chart.chartHead}>
      <div className={chart.chartTitleGroup}>
        <div className={chart.chartTitleBlock}>
          <div className={chart.chartTitle}>{title}</div>
        </div>
      </div>
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
  color,
  footer,
  extra,
  emphasis = 'normal',
  feature,
  metricMap,
  pending
}: {
  title: string;
  metric: string;
  unit: MetricUnit;
  color: string;
  footer?: string;
  extra?: ReactNode;
  emphasis?: 'hero' | 'normal' | 'compact';
  feature: string;
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const shown = redisDisplay(metricMap, metric, unit);
  const loading = pending.has(metric) && shown.value == null;
  const valueColor = shown.value == null ? 'var(--color-text-3)' : color;
  const valueClass = emphasis === 'hero'
    ? 'flex items-baseline gap-2 text-[32px] font-bold leading-none tracking-tight tabular-nums sm:text-[40px]'
    : emphasis === 'compact'
      ? 'flex items-baseline gap-1 text-[20px] font-semibold leading-none tabular-nums'
      : styles.statValue;
  return (
    <section
      className={`${styles.panel} h-full${emphasis === 'hero' ? ' !border-l-4 !border-l-[var(--color-primary)]' : ''}`}
      data-redis-feature={feature}
      data-redis-emphasis={emphasis}
    >
      <FeatureHead title={title} />
      {loading ? (
        <ProDashLoading />
      ) : (
        <div className="flex flex-col gap-2">
          <div className={valueClass} style={{ color: valueColor }}>
            {shown.text}
            {shown.unit ? <span className={styles.statUnit}>{shown.unit}</span> : null}
          </div>
          {extra}
          {footer ? <p className={hintClass}>{footer}</p> : null}
        </div>
      )}
    </section>
  );
}

function PairBars({
  title,
  quiet,
  loading,
  quietText,
  rows
}: {
  title: string;
  quiet: boolean;
  loading: boolean;
  quietText: string;
  rows: ReadonlyArray<{ label: string; display: string; percent: number; color: string }>;
}) {
  return (
    <section className={`${styles.panel} h-full`} data-redis-feature="net">
      <FeatureHead title={title} />
      {loading ? (
        <ProDashLoading />
      ) : quiet ? (
        <p className={quietClass}>{quietText}</p>
      ) : (
        <div className="flex flex-col gap-3">
          {rows.map((row) => (
            <div key={row.label}>
              <div className="mb-1 flex justify-between gap-3 text-[12px]">
                <span className="text-[var(--color-text-1)]">{row.label}</span>
                <span className="tabular-nums text-[var(--color-text-3)]">{row.display}</span>
              </div>
              <Progress
                percent={row.percent}
                showInfo={false}
                strokeColor={row.color}
                trailColor="var(--color-fill-2)"
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function reading(metricMap: RedisMetricMap, name: string, unit: MetricUnit) {
  const shown = redisDisplay(metricMap, name, unit);
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
      <FeatureHead title={text('cardCapacity')} />
      {waiting ? (
        <ProDashLoading />
      ) : state === 'quiet' ? (
        <p className={quietClass}>{text('chartQuiet')}</p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[14px] font-semibold" style={{ color: stateColor }}>{stateLabel}</span>
            {percent != null ? (
              <span className="tabular-nums text-[13px] text-[var(--color-text-2)]">{`${percent.toFixed(1)}%`}</span>
            ) : null}
          </div>
          <p className="m-0 text-[13px] tabular-nums text-[var(--color-text-1)]">
            {text('seriesUsed')} {reading(metricMap, 'redis_used_memory', 'bytes')}
            {state === 'unset' ? null : ` / ${text('seriesLimit')} ${reading(metricMap, 'redis_maxmemory', 'bytes')}`}
          </p>
          {percent != null ? (
            <PressureScale percent={percent} />
          ) : (
            <div className="flex gap-1.5" aria-hidden>
              {Array.from({ length: 5 }, (_, index) => (
                <span key={index} className="h-2 flex-1 rounded-sm bg-[var(--color-fill-2)]" />
              ))}
            </div>
          )}
          <p className={hintClass}>{text('capacityHint')}</p>
        </div>
      )}
    </section>
  );
}

function FragBands({ active }: { active: 'low' | 'ok' | 'high' | null }) {
  const text = useRedisText();
  const items = [
    { key: 'low' as const, label: text('fragLow'), color: TONE_COLOR.near },
    { key: 'ok' as const, label: text('fragOk'), color: TONE_COLOR.ok },
    { key: 'high' as const, label: text('fragHigh'), color: TONE_COLOR.full }
  ];
  return (
    <div className="flex gap-1.5" data-redis-frag={active ?? 'quiet'}>
      {items.map((item) => {
        const on = item.key === active;
        return (
          <span
            key={item.key}
            className="inline-flex h-6 flex-1 items-center justify-center rounded-md text-[12px]"
            style={{
              color: on ? item.color : 'var(--color-text-3)',
              background: on ? `color-mix(in srgb, ${item.color} 14%, var(--color-bg))` : 'var(--color-fill-2)',
              fontWeight: on ? 600 : 400
            }}
          >
            {item.label}
          </span>
        );
      })}
    </div>
  );
}

function fragBand(value: number | null): 'low' | 'ok' | 'high' | null {
  if (value == null) return null;
  if (value < 1) return 'low';
  if (value > 1.5) return 'high';
  return 'ok';
}

function LifecycleCard({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const expired = redisDisplay(metricMap, 'redis_expired_keys_rate', 'cps');
  const evicted = redisDisplay(metricMap, 'redis_evicted_keys_rate', 'cps');
  const loading = (pending.has('redis_expired_keys_rate') || pending.has('redis_evicted_keys_rate'))
    && expired.value == null
    && evicted.value == null;
  const evictedColor = evicted.value != null && evicted.value > 0 ? TONE_COLOR.full : 'var(--color-text-1)';
  const cells = [
    { label: text('seriesExpired'), shown: expired, color: 'var(--color-text-1)' },
    { label: text('seriesEvicted'), shown: evicted, color: evictedColor }
  ];
  return (
    <section className={`${styles.panel} h-full`} data-redis-feature="lifecycle">
      <FeatureHead title={text('cardLifecycle')} />
      {loading ? (
        <ProDashLoading />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {cells.map((cell) => (
              <div key={cell.label} className="min-w-0">
                <div className="text-[12px] text-[var(--color-text-3)]">{cell.label}</div>
                <div className={styles.statValue} style={{ color: cell.shown.value == null ? 'var(--color-text-3)' : cell.color }}>
                  {cell.shown.text}
                  {cell.shown.unit ? <span className={styles.statUnit}>{cell.shown.unit}</span> : null}
                </div>
              </div>
            ))}
          </div>
          <p className={hintClass}>{text('lifecycleHint')}</p>
        </div>
      )}
    </section>
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
  const band = fragBand(frag);
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
            color={fragColor}
            footer={text('fragHint')}
            extra={<FragBands active={band} />}
            metricMap={metricMap}
            pending={pending}
          />
        </div>
      </ProSection>
      <ProSection title={text('sectionLifecycle')}>
        <div className="flex min-w-0 flex-col gap-3">
          <LifecycleCard metricMap={metricMap} pending={pending} />
          <RedisTrendChart spec={lifecycleTrend} metricMap={metricMap} pending={pending} />
        </div>
      </ProSection>
    </Pane>
  );
}

function PenetrationCallout({ warn }: { warn: boolean }) {
  const text = useRedisText();
  const accent = warn ? TONE_COLOR.near : 'var(--color-primary)';
  return (
    <p
      className="m-0 rounded-lg px-3 py-2 text-[13px] leading-5 text-[var(--color-text-2)]"
      data-redis-feature="penetration"
      data-redis-penetration={warn ? 'warn' : 'calm'}
      style={{
        background: `color-mix(in srgb, ${accent} 10%, var(--color-bg))`,
        border: `1px solid color-mix(in srgb, ${accent} 32%, var(--color-border))`
      }}
    >
      <span className="font-semibold text-[var(--color-text-1)]">{text('penetration')}</span>
      {' '}
      {text('penetrationHint')}
    </p>
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
  const loading = (pending.has('redis_keyspace_hits_rate') || pending.has('redis_keyspace_misses_rate'))
    && hits.value == null && misses.value == null;
  const empty = !loading && hits.value == null && misses.value == null;
  const total = Math.max(hits.value ?? 0, 0) + Math.max(misses.value ?? 0, 0);
  const known = hits.value != null || misses.value != null;
  const centerValue = !known
    ? '--'
    : total > 0
      ? `${((Math.max(misses.value ?? 0, 0) / total) * 100).toFixed(1)}%`
      : '0.0%';
  const penetrating = misses.value != null && hits.value != null && misses.value > hits.value && misses.value > 0;
  const rateText = (shown: { text: string; unit: string }) => (shown.unit ? `${shown.text}${shown.unit}` : shown.text);
  return (
    <Pane pane="cache">
      <ProSection title={text('sectionCache')}>
        <div className="grid min-w-0 grid-cols-1 items-stretch gap-3 lg:grid-cols-[minmax(0,1.35fr)_minmax(240px,0.8fr)]">
          <div className="flex min-w-0 flex-col gap-3">
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
                    { name: text('seriesHit'), value: Math.max(hits.value ?? 0, 0), color: REDIS_PALETTE.emerald, display: hits.text },
                    { name: text('seriesMiss'), value: Math.max(misses.value ?? 0, 0), color: REDIS_PALETTE.rose, display: misses.text }
                  ]}
                  infoRows={[
                    { name: text('seriesHit'), color: REDIS_PALETTE.emerald, primary: rateText(hits) },
                    { name: text('seriesMiss'), color: REDIS_PALETTE.rose, primary: rateText(misses) }
                  ]}
                  centerValue={centerValue}
                  centerCaption={text('penetration')}
                  isEmpty={empty}
                  emptyDescription={text('chartQuiet')}
                  styles={ringStyles}
                />
              </div>
            )}
            <PenetrationCallout warn={penetrating} />
          </div>
          <BigNumber
            feature="hit-rate"
            title={text('cardHitRate')}
            metric="redis_keyspace_hitrate"
            unit="percent"
            color={TONE_COLOR.ok}
            footer={text('hitRateHint')}
            metricMap={metricMap}
            pending={pending}
          />
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
  const blocked = redisDisplay(metricMap, 'redis_blocked_clients', 'counts');
  const loading = pending.has('redis_blocked_clients') && blocked.value == null;
  const warn = blocked.value != null && blocked.value > 0;
  const accent = blocked.value == null ? TONE_COLOR.neutral : warn ? TONE_COLOR.full : TONE_COLOR.ok;
  const rejectValue = redisLatest(metricMap, 'redis_rejected_connections_rate');
  return (
    <Pane pane="clients">
      <ProSection title={text('sectionBlocked')}>
        <section
          className={`${styles.panel} h-full`}
          data-redis-feature="blocked"
          data-redis-blocked={loading ? 'loading' : blocked.value == null ? 'quiet' : warn ? 'warn' : 'healthy'}
          style={blocked.value == null ? undefined : {
            background: `color-mix(in srgb, ${accent} 8%, var(--color-bg))`,
            borderColor: `color-mix(in srgb, ${accent} 42%, var(--color-border))`
          }}
        >
          <FeatureHead title={text('cardBlocked')} />
          {loading ? (
            <ProDashLoading />
          ) : blocked.value == null ? (
            <p className={quietClass}>{text('chartQuiet')}</p>
          ) : (
            <div className="flex flex-col gap-2">
              <div className="flex items-baseline gap-2 text-[32px] font-bold leading-none tabular-nums" style={{ color: accent }}>
                {blocked.text}
                {blocked.unit ? <span className={styles.statUnit}>{blocked.unit}</span> : null}
              </div>
              <p className="m-0 text-[14px] font-semibold text-[var(--color-text-1)]">
                {warn ? text('blockedWarn') : text('blockedHealthy')}
              </p>
              <p className={hintClass}>{text('blockedHint')}</p>
            </div>
          )}
        </section>
      </ProSection>
      <ProSection title={text('sectionConnections')}>
        <div className="flex min-w-0 flex-col gap-3">
          <div className={featureGrid}>
            <BigNumber
              feature="clients"
              emphasis="compact"
              title={text('seriesClients')}
              metric="redis_clients"
              unit="counts"
              color="var(--color-text-1)"
              metricMap={metricMap}
              pending={pending}
            />
            <BigNumber
              feature="rejected"
              emphasis="compact"
              title={text('cardRejected')}
              metric="redis_rejected_connections_rate"
              unit="cps"
              color={rejectValue != null && rejectValue > 0 ? TONE_COLOR.full : 'var(--color-text-1)'}
              metricMap={metricMap}
              pending={pending}
            />
          </div>
          <RedisTrendChart spec={rejectTrend} metricMap={metricMap} pending={pending} />
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
  const inbound = redisLatest(metricMap, 'redis_total_net_input_bytes_rate');
  const outbound = redisLatest(metricMap, 'redis_total_net_output_bytes_rate');
  const loading = pending.has('redis_total_net_input_bytes_rate') && inbound == null && outbound == null;
  const max = Math.max(inbound ?? 0, outbound ?? 0);
  const share = (value: number | null) => (max > 0 && value != null ? (value / max) * 100 : 0);
  return (
    <Pane pane="throughput">
      <ProSection title={text('sectionOps')}>
        <div className="grid min-w-0 grid-cols-1 items-stretch gap-3 lg:grid-cols-[minmax(0,1.7fr)_minmax(220px,0.75fr)]">
          <BigNumber
            feature="ops"
            emphasis="hero"
            title={text('focusOps')}
            metric="redis_instantaneous_ops_per_sec"
            unit="cps"
            color="var(--color-text-1)"
            footer={text('opsHint')}
            metricMap={metricMap}
            pending={pending}
          />
          <BigNumber
            feature="command-rate"
            title={text('seriesCommands')}
            metric="redis_total_commands_processed_rate"
            unit="cps"
            color="var(--color-text-1)"
            footer={text('commandHint')}
            metricMap={metricMap}
            pending={pending}
          />
        </div>
      </ProSection>
      <ProSection title={text('sectionTrends')}>
        <RedisTrendChart spec={opsTrend} metricMap={metricMap} pending={pending} />
      </ProSection>
      <ProSection title={text('sectionNetwork')}>
        <PairBars
          title={text('cardNetCompare')}
          quiet={!loading && inbound == null && outbound == null}
          loading={loading}
          quietText={text('chartQuiet')}
          rows={[
            {
              label: text('seriesNetIn'),
              display: reading(metricMap, 'redis_total_net_input_bytes_rate', 'byteps'),
              percent: share(inbound),
              color: REDIS_PALETTE.blue
            },
            {
              label: text('seriesNetOut'),
              display: reading(metricMap, 'redis_total_net_output_bytes_rate', 'byteps'),
              percent: share(outbound),
              color: REDIS_PALETTE.emerald
            }
          ]}
        />
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
