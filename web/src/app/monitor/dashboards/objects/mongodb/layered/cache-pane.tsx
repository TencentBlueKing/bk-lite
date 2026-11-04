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
  const waiting = percent == null && (
    pending.has('mongodb_wtcache_current_bytes') || pending.has('mongodb_wtcache_max_bytes_configured')
  );
  const tone = percent == null ? null : pressureOf(percent);
  const used = byteText(metricMap, 'mongodb_wtcache_current_bytes');
  const limit = byteText(metricMap, 'mongodb_wtcache_max_bytes_configured');
  const fill = percent == null ? 0 : Math.min(100, Math.max(0, percent));
  return (
    <section
      id="mongo-cache-usage"
      className={`${classic.panel} ${host.chartPanel} flex h-full flex-col`}
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
      {waiting ? <ProDashLoading /> : percent == null ? (
        <div className={`${host.chartEmpty} flex-1`}>
          <span className="text-[13px] font-semibold text-[var(--color-text-2)]">本窗口暂无数据</span>
        </div>
      ) : (
        <div className="flex flex-1 flex-col justify-center gap-3">
          <div
            className="text-[28px] font-bold leading-none tabular-nums"
            style={{ color: tone ? PRESSURE_COLOR[tone] : undefined }}
          >
            {formatMongoPercent(percent)}
          </div>
          {used && limit ? (
            <p className="m-0 text-[13px] tabular-nums text-[var(--color-text-1)]">
              {`已用 ${used} / 上限 ${limit}`}
            </p>
          ) : null}
          <div
            className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-fill-2)]"
            role="meter"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Number(fill.toFixed(1))}
            aria-label="缓存使用率"
            data-mongodb-cache-meter={tone || 'empty'}
          >
            <span
              className="block h-full rounded-full"
              style={{ width: `${fill}%`, background: tone ? PRESSURE_COLOR[tone] : undefined }}
            />
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
        <div className={host.chartGrid2} data-mongodb-zone="cache">
          <UsageCard metricMap={metricMap} pending={pendingMetricNames} />
          <MongoTrend
            anchor="cache-usage-trend"
            title="缓存使用率趋势"
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
          <MongoTrend
            anchor="cache-bytes"
            title="缓存已用与上限"
            body="WiredTiger 缓存当前占用与配置上限对照。"
            series={[
              { name: 'mongodb_wtcache_current_bytes', label: '已用', color: MONGODB_PALETTE.blue, unit: 'bytes' },
              { name: 'mongodb_wtcache_max_bytes_configured', label: '上限', color: MONGODB_PALETTE.slate, unit: 'bytes' }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
          />
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
          <div className="min-w-0 min-[1101px]:col-span-2">
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
        <div className={host.chartGrid2} data-mongodb-zone="memory">
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
        </div>
      </ProSection>
    </div>
  );
}
