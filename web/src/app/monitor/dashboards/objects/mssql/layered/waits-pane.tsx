'use client';

import { useEffect, useState, type Key } from 'react';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { ProDashLoading, ProSection, ThinTimeSeries } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import classic from '../../host/index.module.scss';
import { MSSQL_SIDE_PLOT_PX } from './display-units';
import { buildSearchParams } from '../../../shared/utils';
import { mssqlCardFace, mssqlDeferEmpty } from './card-face';
import { MssqlHint } from './hint';
import { MSSQL_PRO_NAMES, MSSQL_PRO_PALETTE, MSSQL_PRO_WAIT_CATEGORY_QUERY } from './queries';
import { joinMetric, waitCategoryChart, type MssqlMetricMap } from './series';
import { MssqlSideReadout, MssqlTrend } from './trend';

const WAIT_BODY = '各类等待消耗的时间，区分为总等待、信号等待和资源等待。信号等待偏高通常与 CPU 调度有关，资源等待偏高通常与锁、I/O 等外部资源有关。';

export default function WaitsPane({
  metricMap,
  pendingMetricNames,
  batchLoading = false,
  instanceId,
  monitorObjectId,
  idValues,
  instanceIdKeys,
  timeValues,
  minStepSeconds,
  reloadKey
}: {
  metricMap: MssqlMetricMap;
  pendingMetricNames: ReadonlySet<string>;
  batchLoading?: boolean;
  instanceId: Key;
  monitorObjectId: Key;
  idValues: string[];
  instanceIdKeys: string[];
  timeValues: TimeValuesProps;
  minStepSeconds?: number;
  reloadKey: number;
}) {
  const { getInstanceQuery } = useViewApi();
  const [categories, setCategories] = useState<ReturnType<typeof waitCategoryChart>>({ data: [], legends: [] });
  const [phase, setPhase] = useState<'loading' | 'ready'>('loading');
  const categoryFace = mssqlCardFace(
    mssqlDeferEmpty(categories.data.length > 0, phase === 'loading', batchLoading),
    categories.data.length > 0
  );
  const identity = `${idValues.join('\u0001')}|${instanceIdKeys.join('\u0001')}|${reloadKey}`;

  useEffect(() => {
    if (!idValues.length || !instanceId) {
      setCategories({ data: [], legends: [] });
      setPhase('ready');
      return undefined;
    }
    let active = true;
    setPhase('loading');
    getInstanceQuery(buildSearchParams(
      MSSQL_PRO_WAIT_CATEGORY_QUERY,
      'msps',
      idValues,
      instanceIdKeys,
      timeValues,
      undefined,
      false,
      minStepSeconds,
      { monitorObjectId: String(monitorObjectId || ''), instanceId: String(instanceId) }
    )).then((result) => {
      if (!active) return;
      setCategories(waitCategoryChart(result));
      setPhase('ready');
    }).catch(() => {
      if (!active) return;
      setCategories({ data: [], legends: [] });
      setPhase('ready');
    });
    return () => {
      active = false;
    };
  }, [
    getInstanceQuery,
    idValues,
    identity,
    instanceId,
    instanceIdKeys,
    minStepSeconds,
    monitorObjectId,
    timeValues
  ]);

  return (
    <div data-mssql-pane="waits" className="contents">
      <ProSection title="等待构成">
        <MssqlTrend
          anchor="wait-mix"
          title="等待时间构成"
          body={WAIT_BODY}
          series={[
            {
              name: MSSQL_PRO_NAMES.waitTime,
              label: '总等待',
              color: MSSQL_PRO_PALETTE.indigo,
              unit: 'msps'
            },
            {
              name: MSSQL_PRO_NAMES.signalWait,
              label: '信号等待',
              color: MSSQL_PRO_PALETTE.orange,
              unit: 'msps'
            },
            {
              name: MSSQL_PRO_NAMES.resourceWait,
              label: '资源等待',
              color: MSSQL_PRO_PALETTE.cyan,
              unit: 'msps'
            }
          ]}
          metricMap={metricMap}
          pending={pendingMetricNames}
          batchLoading={batchLoading}
        />
      </ProSection>
      <ProSection
        title="等待类别 Top"
        hint={(
          <MssqlHint
            kind="mssql-wait-top"
            title="等待类别 Top"
            body="按等待类别汇总，查看哪一类等待占用时间最多。类别名按源端原文展示。"
          />
        )}
      >
        <div id="mssql-wait-top" className="min-w-0 scroll-mt-3" data-mssql-chart="wait-top" data-mssql-face={categoryFace}>
          {categoryFace === 'ready' ? (
            <MssqlSideReadout
              items={categories.legends}
              chart={(
                <ThinTimeSeries
                  title=""
                  unit="msps"
                  pinAxisZero
                  keepLegend
                  hideLegend
                  data={categories.data}
                  legends={categories.legends}
                  formatReading={(value) => joinMetric(value, 'msps')}
                  plotHeight={MSSQL_SIDE_PLOT_PX}
                />
              )}
            />
          ) : (
            <section className={`${classic.panel} ${host.chartPanel}`}>
              <div className="flex min-h-16 items-center justify-center">
                {categoryFace === 'loading' ? <ProDashLoading /> : (
                  <span className="text-[13px] font-semibold text-[var(--color-text-2)]">本窗口暂无数据</span>
                )}
              </div>
            </section>
          )}
        </div>
      </ProSection>
      <ProSection title="锁与死锁">
        <div className={host.chartGrid3}>
          <MssqlTrend
            anchor="locks"
            title="锁等待"
            body="锁等待发生的频繁程度。持续走高说明并发争用在加重。"
            series={[{
              name: MSSQL_PRO_NAMES.lockWaits,
              label: '锁等待',
              color: MSSQL_PRO_PALETTE.orange,
              unit: 'cps'
            }]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
          <MssqlTrend
            anchor="blocked"
            title="阻塞进程数"
            body="当前被其他会话堵住、正在等待的进程个数。"
            counts
            series={[{
              name: MSSQL_PRO_NAMES.blocked,
              label: '阻塞进程数',
              color: MSSQL_PRO_PALETTE.rose,
              unit: 'counts'
            }]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
          <MssqlTrend
            anchor="deadlocks"
            title="死锁次数"
            body="各时间点上发生的死锁次数，用于观察冲突是否在窗口内反复出现。"
            counts
            series={[{
              name: MSSQL_PRO_NAMES.deadlocks,
              label: '死锁次数',
              color: MSSQL_PRO_PALETTE.rose,
              unit: 'counts'
            }]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
        </div>
      </ProSection>
      <ProSection title="调度与请求">
        <div className={host.chartGrid2}>
          <MssqlTrend
            anchor="schedulers"
            title="调度器队列"
            body="当前可运行但尚未获得 CPU 的任务数，以及调度器上的活动工作线程数。可运行任务持续堆积，说明 CPU 可能供不应求。"
            counts
            series={[
              {
                name: MSSQL_PRO_NAMES.runnable,
                label: '可运行任务',
                color: MSSQL_PRO_PALETTE.amber,
                unit: 'counts'
              },
              {
                name: MSSQL_PRO_NAMES.workers,
                label: '活动工作线程',
                color: MSSQL_PRO_PALETTE.blue,
                unit: 'counts'
              }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
          <MssqlTrend
            anchor="requests"
            title="请求耗时画像"
            body="正在执行的请求在计算、等待等方面的耗时构成。"
            series={[
              {
                name: MSSQL_PRO_NAMES.requestElapsed,
                label: '总耗时',
                color: MSSQL_PRO_PALETTE.indigo,
                unit: 'msps'
              },
              {
                name: MSSQL_PRO_NAMES.requestCpu,
                label: '计算',
                color: MSSQL_PRO_PALETTE.blue,
                unit: 'msps'
              },
              {
                name: MSSQL_PRO_NAMES.requestWait,
                label: '等待',
                color: MSSQL_PRO_PALETTE.orange,
                unit: 'msps'
              }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
        </div>
      </ProSection>
    </div>
  );
}
