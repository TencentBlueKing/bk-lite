'use client';

import { useTranslation } from '@/utils/i18n';
import { ProSection, ThinTimeSeries } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import { MssqlHint } from './hint';
import { MSSQL_PRO_NAMES, MSSQL_PRO_PALETTE } from './queries';
import { mssqlDeferEmpty } from './card-face';
import { clerkChart, type MssqlMetricMap } from './series';
import { MssqlSeriesReadout, MssqlTrend } from './trend';

const HIT_BODY = '缓冲池满足的数据页读取占比。偏低说明热点数据未充分驻留内存、读盘偏多。\n命中 ÷（命中 + 未命中）× 100%\n分母为 0 时显示 —，不用 0% 顶替。';

export default function BufferPane({
  metricMap,
  pendingMetricNames,
  batchLoading = false
}: {
  metricMap: MssqlMetricMap;
  pendingMetricNames: ReadonlySet<string>;
  batchLoading?: boolean;
}) {
  const { t } = useTranslation();
  const memoryTitle = t('monitor.dashboards.text.mssqlInstanceMemory', '实例内存');
  const clerks = clerkChart(metricMap);
  const clerkPending = mssqlDeferEmpty(
    clerks.data.length > 0,
    pendingMetricNames.has(MSSQL_PRO_NAMES.clerks),
    batchLoading
  );
  return (
    <div data-mssql-pane="buffer_memory" className="contents">
      <ProSection title="缓冲池">
        <div className={host.chartGrid2}>
          <MssqlTrend
            anchor="hit"
            title="缓冲池命中率"
            body={HIT_BODY}
            percent
            series={[{
              name: MSSQL_PRO_NAMES.hit,
              label: '缓冲池命中率',
              color: MSSQL_PRO_PALETTE.emerald,
              unit: 'percent'
            }]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
          <MssqlTrend
            anchor="ple"
            title="页生命周期期望"
            body="数据页在缓冲池中预计可停留的时间。明显变短通常意味着内存压力上升。"
            series={[{
              name: MSSQL_PRO_NAMES.pageLife,
              label: '页生命周期期望',
              color: MSSQL_PRO_PALETTE.cyan,
              unit: 's'
            }]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
        </div>
      </ProSection>
      <ProSection title="内存">
        <div className={host.chartGrid2}>
          <MssqlTrend
            anchor="server-memory"
            title={memoryTitle}
            body={t(
              'monitor.dashboards.text.mssqlInstanceMemoryBody',
              '当前已提交给 SQL Server 的内存，以及实例希望使用的目标内存。两者接近属于常见稳态；出现持续缺口时再关注内存配置与负载。'
            )}
            series={[
              {
                name: MSSQL_PRO_NAMES.totalMemory,
                label: t('monitor.dashboards.text.mssqlMemoryCurrent', '当前'),
                color: MSSQL_PRO_PALETTE.indigo,
                unit: 'kibibytes'
              },
              {
                name: MSSQL_PRO_NAMES.targetMemory,
                label: t('monitor.dashboards.text.mssqlMemoryTarget', '目标'),
                color: MSSQL_PRO_PALETTE.neutral,
                unit: 'kibibytes'
              }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
          <MssqlTrend
            anchor="checkpoint"
            title="检查点与惰性写入"
            body="检查点写回脏页的速率，以及内存紧张时惰性写入腾出缓冲的速率。"
            series={[
              {
                name: MSSQL_PRO_NAMES.checkpoint,
                label: '检查点',
                color: MSSQL_PRO_PALETTE.blue,
                unit: 'cps'
              },
              {
                name: MSSQL_PRO_NAMES.lazyWrites,
                label: '惰性写入',
                color: MSSQL_PRO_PALETTE.indigo,
                unit: 'cps'
              }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
        </div>
      </ProSection>
      <ProSection title="授予与编译">
        <div className={host.chartGrid2}>
          <MssqlTrend
            anchor="grants"
            title="内存授予"
            body="已获得工作区内存的请求数，以及仍在排队等待授予的请求数。等待数持续大于 0，说明查询在争用内存。"
            counts
            series={[
              {
                name: MSSQL_PRO_NAMES.grantsOutstanding,
                label: '已授予',
                color: MSSQL_PRO_PALETTE.blue,
                unit: 'counts'
              },
              {
                name: MSSQL_PRO_NAMES.grantsPending,
                label: '等待授予',
                color: MSSQL_PRO_PALETTE.orange,
                unit: 'counts'
              }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
          <MssqlTrend
            anchor="compile"
            title="编译与重编译"
            body="每秒新编译与重新编译的语句计划数。重编译偏高时，计划缓存可能不够稳定。"
            series={[
              {
                name: MSSQL_PRO_NAMES.compilations,
                label: '编译',
                color: MSSQL_PRO_PALETTE.cyan,
                unit: 'cps'
              },
              {
                name: MSSQL_PRO_NAMES.recompilations,
                label: '重编译',
                color: MSSQL_PRO_PALETTE.amber,
                unit: 'cps'
              }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
        </div>
      </ProSection>
      <ProSection title="构成">
        <div id="mssql-clerks" className="min-w-0 scroll-mt-3" data-mssql-chart="clerks">
          <ThinTimeSeries
            title="内存用途构成"
            hintNode={(
              <MssqlHint
                kind="mssql-clerks"
                title="内存用途构成"
                body="按用途查看各类内存占用的大小，便于判断内存主要花在哪里。"
              />
            )}
            unit="kibibytes"
            pinAxisZero
            keepLegend
            hideLegend
            loading={clerkPending}
            emptyText="本窗口暂无数据"
            data={clerks.data}
            legends={clerks.legends}
            formatReading={clerks.formatReading}
          />
          {clerks.data.length > 0 ? (
            <div
              className="mt-4 overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]"
              data-mssql-series-frame=""
            >
              <MssqlSeriesReadout items={clerks.legends} />
            </div>
          ) : null}
        </div>
      </ProSection>
    </div>
  );
}
