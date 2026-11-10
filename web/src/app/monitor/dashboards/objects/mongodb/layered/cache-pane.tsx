'use client';

import { ProDashLoading, ProSection } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import classic from '../../host/index.module.scss';
import { MongoHint } from './hint';
import { MONGODB_PALETTE } from './metrics';
import { MongoTrend } from './trend';
import {
  formatMongoPercent,
  formatMongoReading,
  mongoLatest,
  mongoRatioPercent,
  mongoRatioPoints,
  type MongoMetricMap
} from './series';

const PRESSURE_COLOR = {
  ok: 'var(--color-success)',
  near: 'var(--color-warning)',
  full: 'var(--color-fail)'
} as const;

const pressureOf = (percent: number) => {
  if (percent >= 95) return 'full' as const;
  if (percent >= 80) return 'near' as const;
  return 'ok' as const;
};

const USAGE_BODY = 'WiredTiger 缓存已用容量占总上限的比例。\n已用 ÷ 上限 × 100%\n分母为 0 时显示 —，不用 0% 顶替。';
const DIRTY_BODY = '缓存中尚未落盘的脏数据比例。\n脏数据 ÷ 当前缓存 × 100%\n分母为 0 时显示 —，不用 0% 顶替。';

/** 低占用软顶。忽略 null 后的窗口 vmax：≤5 → 10，≤20 → 25，≤50 → 60，否则 100。 */
export const cacheUsageAxisMax = (vmax: number) => {
  if (!Number.isFinite(vmax) || vmax <= 5) return 10;
  if (vmax <= 20) return 25;
  if (vmax <= 50) return 60;
  return 100;
};

/** 窗口内采样（已忽略 null）对应的 0–软顶轴。单位仍是 %。 */
export const cacheUsageBoundsFromSamples = (samples: readonly number[]) => {
  let vmax = Number.NEGATIVE_INFINITY;
  samples.forEach((value) => {
    if (typeof value === 'number' && Number.isFinite(value) && value > vmax) vmax = value;
  });
  return { min: 0, max: cacheUsageAxisMax(vmax) };
};

/** ≥1100 左右约 0.36fr : 1fr；更窄则上 KPI 下趋势。气口 16px，不再套第二层卡边。 */
const USAGE_COMPOSE_GRID = 'grid min-h-0 w-full min-w-0 flex-1 grid-cols-1 items-stretch gap-4 min-[1100px]:grid-cols-[minmax(200px,0.36fr)_minmax(0,1fr)]';

function byteText(metricMap: MongoMetricMap, name: string) {
  const latest = mongoLatest(metricMap, name);
  if (latest == null) return '';
  return formatMongoReading(latest, 'bytes');
}

function UsageCard({
  metricMap,
  pending
}: {
  metricMap: MongoMetricMap;
  pending: ReadonlySet<string>;
}) {
  const percent = mongoRatioPercent(
    metricMap,
    'mongodb_wtcache_current_bytes',
    'mongodb_wtcache_max_bytes_configured'
  );
  const usedLatest = mongoLatest(metricMap, 'mongodb_wtcache_current_bytes');
  const limitLatest = mongoLatest(metricMap, 'mongodb_wtcache_max_bytes_configured');
  const waiting = percent == null && (usedLatest == null || limitLatest == null) && (
    pending.has('mongodb_wtcache_current_bytes') || pending.has('mongodb_wtcache_max_bytes_configured')
  );
  const tone = percent == null ? null : pressureOf(percent);
  const used = byteText(metricMap, 'mongodb_wtcache_current_bytes');
  const limit = byteText(metricMap, 'mongodb_wtcache_max_bytes_configured');
  const note = used && limit ? `已用 ${used} / 上限 ${limit}` : '';
  const quiet = !waiting && percent == null && !note;
  return (
    <div
      id="mongo-cache-usage"
      className="flex h-full min-h-0 min-w-0 flex-col"
      data-mongodb-chart="cache-usage"
      data-mongodb-cache={waiting ? 'loading' : percent == null ? 'empty' : tone}
    >
      <div className={host.chartHead}>
        <div className={host.chartTitle}>
          <span className="inline-flex items-center gap-1">
            缓存使用率
            <MongoHint kind="mongo-cache-usage" title="缓存使用率" body={USAGE_BODY} />
          </span>
        </div>
      </div>
      {waiting ? (
        <div className="flex flex-1 items-center justify-center">
          <ProDashLoading />
        </div>
      ) : quiet ? (
        <div className="flex flex-1 flex-col justify-center gap-2">
          <div
            className="text-[30px] font-bold leading-none tabular-nums text-[var(--color-text-2)]"
            data-mongodb-cache-reading=""
          >
            —
          </div>
          <p className="m-0 text-[13px] leading-5 text-[var(--color-text-3)]">本窗口暂无数据</p>
        </div>
      ) : (
        <div className="flex flex-1 flex-col justify-center">
          <div
            className="text-[30px] font-bold leading-none tabular-nums"
            data-mongodb-cache-reading=""
            style={{ color: tone ? PRESSURE_COLOR[tone] : 'var(--color-text-2)' }}
          >
            {formatMongoPercent(percent)}
          </div>
          {note ? (
            <div className="mt-3 flex w-full flex-col gap-0.5" data-mongodb-cache-note="">
              <p className="m-0 text-[13px] leading-5 tabular-nums text-[var(--color-text-3)]">已用 {used}</p>
              <p className="m-0 text-[13px] leading-5 tabular-nums text-[var(--color-text-3)]">上限 {limit}</p>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

export default function CachePane({
  metricMap,
  pendingMetricNames
}: {
  metricMap: MongoMetricMap;
  pendingMetricNames: ReadonlySet<string>;
}) {
  const usagePoints = mongoRatioPoints(
    metricMap,
    'mongodb_wtcache_current_bytes',
    'mongodb_wtcache_max_bytes_configured'
  );
  const dirtyPoints = mongoRatioPoints(
    metricMap,
    'mongodb_wtcache_tracked_dirty_bytes',
    'mongodb_wtcache_current_bytes'
  );
  return (
    <div data-mongodb-pane="cache" className="contents">
      <ProSection title="缓存">
        <div className="flex min-w-0 flex-col gap-3" data-mongodb-zone="cache">
          <section
            className={`${classic.panel} ${host.chartPanel} flex min-h-[180px] min-w-0 flex-col`}
            data-mongodb-cache-layout="usage-compose"
          >
            <div className={USAGE_COMPOSE_GRID}>
              <UsageCard metricMap={metricMap} pending={pendingMetricNames} />
              <MongoTrend
                bare
                anchor="cache-usage-trend"
                title="趋势"
                hintTitle="缓存使用率"
                body={USAGE_BODY}
                series={[{
                  name: 'mongodb_wtcache_current_bytes',
                  label: '缓存使用率',
                  color: MONGODB_PALETTE.blue,
                  unit: 'percent'
                }]}
                metricMap={metricMap}
                pending={pendingMetricNames}
                pendingNames={['mongodb_wtcache_current_bytes', 'mongodb_wtcache_max_bytes_configured']}
                points={usagePoints}
                resolveValueBounds={cacheUsageBoundsFromSamples}
                areaOpacity={0.12}
                keepSeriesColor
                showHint={false}
                mutedTitle
                percent
              />
            </div>
          </section>
          <div className={host.chartGrid2}>
            <MongoTrend
              anchor="dirty"
              title="脏数据占比"
              body={DIRTY_BODY}
              series={[{
                name: 'mongodb_wtcache_tracked_dirty_bytes',
                label: '脏数据占比',
                color: MONGODB_PALETTE.orange,
                unit: 'percent'
              }]}
              metricMap={metricMap}
              pending={pendingMetricNames}
              pendingNames={['mongodb_wtcache_tracked_dirty_bytes', 'mongodb_wtcache_current_bytes']}
              points={dirtyPoints}
              percent
            />
            <MongoTrend
              anchor="dirty-bytes"
              title="脏数据量"
              body="WiredTiger 缓存中尚未落盘的脏数据大小。"
              series={[{
                name: 'mongodb_wtcache_tracked_dirty_bytes',
                label: '脏数据',
                color: MONGODB_PALETTE.orange,
                unit: 'bytes'
              }]}
              metricMap={metricMap}
              pending={pendingMetricNames}
            />
          </div>
        </div>
      </ProSection>
      <ProSection title="内存">
        <div
          className={host.chartGrid3}
          data-mongodb-zone="memory"
          data-mongodb-memory-layout="equal-3"
        >
          <MongoTrend
            anchor="memory"
            title="常驻与虚拟内存"
            body="进程常驻内存与虚拟内存对照，用于观察内存膨胀。"
            series={[
              { name: 'mongodb_resident_megabytes', label: '常驻内存', color: MONGODB_PALETTE.blue, unit: 'mebibytes' },
              { name: 'mongodb_vsize_megabytes', label: '虚拟内存', color: MONGODB_PALETTE.slate, unit: 'mebibytes' }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
          />
          <MongoTrend
            anchor="tcmalloc"
            title="分配器已分配"
            body="tcmalloc 当前已分配的内存，作为分配器占用旁证。"
            series={[{
              name: 'mongodb_tcmalloc_current_allocated_bytes',
              label: '已分配',
              color: MONGODB_PALETTE.cyan,
              unit: 'bytes'
            }]}
            metricMap={metricMap}
            pending={pendingMetricNames}
          />
          <MongoTrend
            anchor="page-faults"
            title="缺页频率"
            body="每秒缺页次数。升高通常意味着工作集未能很好落在内存中。"
            series={[{
              name: 'mongodb_page_faults_rate',
              label: '缺页',
              color: MONGODB_PALETTE.red,
              unit: 'cps'
            }]}
            metricMap={metricMap}
            pending={pendingMetricNames}
          />
        </div>
      </ProSection>
    </div>
  );
}
