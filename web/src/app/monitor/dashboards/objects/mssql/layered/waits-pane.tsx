'use client';

import { useEffect, useState, type Key } from 'react';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { ProDashLoading, ProSection } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import { HorizontalBarPanel } from '../../../shared/widgets';
import type { BarItem } from '../../../shared/widgets';
import { buildSearchParams, topLabelBars } from '../../../shared/utils';
import { asRangeQueryResult } from '../../../shared/utils/metric-series';
import styles from '../index.module.scss';
import { mssqlCardFace } from './card-face';
import { MssqlHint } from './hint';
import { MSSQL_PRO_NAMES, MSSQL_PRO_PALETTE, MSSQL_PRO_WAIT_CATEGORY_QUERY } from './queries';
import type { MssqlMetricMap } from './series';
import { MssqlTrend } from './trend';

const WAIT_BODY = '各类等待消耗的时间，区分为总等待、信号等待和资源等待。信号等待偏高通常与 CPU 调度有关，资源等待偏高通常与锁、I/O 等外部资源有关。';

export default function WaitsPane({
  metricMap,
  pendingMetricNames,
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
  instanceId: Key;
  monitorObjectId: Key;
  idValues: string[];
  instanceIdKeys: string[];
  timeValues: TimeValuesProps;
  minStepSeconds?: number;
  reloadKey: number;
}) {
  const { getInstanceQuery } = useViewApi();
  const [categories, setCategories] = useState<BarItem[]>([]);
  const [phase, setPhase] = useState<'loading' | 'ready'>('loading');
  const categoryFace = mssqlCardFace(phase === 'loading', categories.length > 0);
  const identity = `${idValues.join('\u0001')}|${instanceIdKeys.join('\u0001')}|${reloadKey}`;

  useEffect(() => {
    if (!idValues.length || !instanceId) {
      setCategories([]);
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
      setCategories(topLabelBars(asRangeQueryResult(result), 'msps', MSSQL_PRO_PALETTE.indigo, ['wait_category']));
      setPhase('ready');
    }).catch(() => {
      if (!active) return;
      setCategories([]);
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
        <div className={host.chartGrid2}>
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
          />
          <div id="mssql-wait-top" className="min-w-0 scroll-mt-3" data-mssql-chart="wait-top">
            <HorizontalBarPanel
              styles={styles}
              className="h-full"
              title={(
                <span className="inline-flex items-center gap-1">
                  等待类别 Top
                  <MssqlHint
                    kind="mssql-wait-top"
                    title="等待类别 Top"
                    body="按等待类别汇总，查看哪一类等待占用时间最多。"
                  />
                </span>
              )}
              items={categoryFace === 'ready' ? categories : []}
              placeholder={categoryFace === 'loading' ? <ProDashLoading /> : categoryFace === 'empty' ? (
                <span className="text-[13px] font-semibold text-[var(--color-text-2)]">本窗口暂无数据</span>
              ) : undefined}
            />
          </div>
        </div>
      </ProSection>
      <ProSection title="锁与死锁">
        <div className={host.chartGrid2}>
          <MssqlTrend
            anchor="locks"
            title="锁等待与阻塞"
            body="锁等待发生的频繁程度，以及当前被堵住的进程个数，用于观察并发争用是否在加重。"
            dualAxis
            series={[
              {
                name: MSSQL_PRO_NAMES.lockWaits,
                label: '锁等待',
                color: MSSQL_PRO_PALETTE.orange,
                unit: 'cps'
              },
              {
                name: MSSQL_PRO_NAMES.blocked,
                label: '阻塞进程',
                color: MSSQL_PRO_PALETTE.rose,
                unit: 'counts'
              }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
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
          />
        </div>
      </ProSection>
    </div>
  );
}
