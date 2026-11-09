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
    <section
      id="mongo-cache-usage"
      className={`${classic.panel} ${host.chartPanel} flex h-full min-h-0 flex-col`}
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
        <div className={`${host.chartEmpty} flex-1`}>
          <span className="text-[13px] font-semibold text-[var(--color-text-2)]">本窗口暂无数据</span>
        </div>
      ) : (
        <div className="flex flex-1 flex-col justify-center">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <div
              className="text-[28px] font-bold leading-none tabular-nums"
              data-mongodb-cache-reading=""
              style={{ color: tone ? PRESSURE_COLOR[tone] : undefined }}
            >
              {formatMongoPercent(percent)}
            </div>
            {note ? (
              <p
                className="m-0 min-w-0 text-[13px] leading-5 tabular-nums text-[var(--color-text-3)]"
                data-mongodb-cache-note=""
              >
                {note}
              </p>
            ) : null}
          </div>
        </div>
      )}
    </section>
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
          <div className={host.chartGrid2} data-mongodb-cache-layout="usage-pair">
            <UsageCard metricMap={metricMap} pending={pendingMetricNames} />
            <MongoTrend
              anchor="cache-usage-trend"
              title="缓存使用率趋势"
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
              percent
            />
          </div>
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
