'use client';

import { useEffect, useState, type Key } from 'react';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { ProDashLoading, ProSection } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import classic from '../../host/index.module.scss';
import { BarList } from '../../../shared/widgets';
import type { BarItem } from '../../../shared/widgets';
import { buildSearchParams, runWithConcurrency } from '../../../shared/utils';
import { MSSQL_TOP_DB_QUERIES } from '../queries';
import { topDbBars } from '../parse';
import styles from '../index.module.scss';
import { mssqlCardFace, mssqlDeferEmpty } from './card-face';
import { MssqlHint } from './hint';
import { MSSQL_PRO_NAMES, MSSQL_PRO_PALETTE } from './queries';
import { mssqlLockedReading } from './display-units';
import {
  formatPercentPoint,
  readVolumeUsage,
  volumeUsagePoints,
  type MssqlMetricMap
} from './series';
import { MssqlTrend } from './trend';

const VOLUME_BODY = '数据与日志所在卷已使用空间占总容量的比例。\n已用 ÷ 总量 × 100%\n分母为 0 时显示 —，不用 0% 顶替。';

const RANK_LABEL = {
  read_latency: '读取延迟',
  write_latency: '写入延迟',
  io_rate: '读写繁忙'
} as const;

type RankKey = keyof typeof RANK_LABEL;

const tightenRankDisplay = (display: string) => display.replace(/\.00(?=\D|$)/, '');

export default function IoPane({
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
  const [bars, setBars] = useState<Record<string, BarItem[]>>({});
  const [rankPhase, setRankPhase] = useState<'loading' | 'ready'>('loading');
  const usage = readVolumeUsage(metricMap);
  const usagePoints = volumeUsagePoints(metricMap);
  const volumePending = mssqlDeferEmpty(
    usage.state !== 'empty',
    pendingMetricNames.has(MSSQL_PRO_NAMES.volumeUsed)
      || pendingMetricNames.has(MSSQL_PRO_NAMES.volumeTotal),
    batchLoading
  );
  const volumeFace = mssqlCardFace(volumePending, usage.state !== 'empty');
  const identity = `${idValues.join('\u0001')}|${instanceIdKeys.join('\u0001')}|${reloadKey}`;

  useEffect(() => {
    if (!idValues.length || !instanceId) {
      setBars({});
      setRankPhase('ready');
      return undefined;
    }
    let active = true;
    setRankPhase('loading');
    runWithConcurrency(MSSQL_TOP_DB_QUERIES, 3, async (query) => (
      getInstanceQuery(buildSearchParams(
        query.query,
        query.unit,
        idValues,
        instanceIdKeys,
        timeValues,
        undefined,
        false,
        minStepSeconds,
        { monitorObjectId: String(monitorObjectId || ''), instanceId: String(instanceId) }
      ))
        .then((result) => [query.key, topDbBars(result, query.unit, query.color)] as const)
        .catch(() => [query.key, [] as BarItem[]] as const)
    )).then((entries) => {
      if (!active) return;
      setBars(Object.fromEntries(entries));
      setRankPhase('ready');
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

  const rankGroups = MSSQL_TOP_DB_QUERIES.map((query) => {
    const raw = bars[query.key] || [];
    const peak = raw.reduce((max, item) => Math.max(max, Math.abs(item.value)), 0);
    const format = query.unit === 'ms' ? mssqlLockedReading('ms', peak) : null;
    const items = raw.map((item) => ({
      ...item,
      display: format ? format(item.value) : tightenRankDisplay(item.display)
    }));
    const face = mssqlCardFace(
      mssqlDeferEmpty(items.length > 0, rankPhase === 'loading', batchLoading),
      items.length > 0
    );
    return { key: query.key as RankKey, label: RANK_LABEL[query.key as RankKey], items, face };
  });
  const volumePeak = Math.max(Math.abs(usage.used ?? 0), Math.abs(usage.total ?? 0));
  const volumeFormat = mssqlLockedReading('bytes', volumePeak);
  const usedText = usage.used == null || !volumeFormat ? '' : volumeFormat(usage.used);
  const totalText = usage.total == null || !volumeFormat ? '' : volumeFormat(usage.total);
  const note = usedText && totalText ? `已用 ${usedText} / 总量 ${totalText}` : '';

  return (
    <div data-mssql-pane="io_storage" className="contents">
      <ProSection title="文件访问">
        <div className={host.chartGrid2}>
          <MssqlTrend
            anchor="latency"
            title="读写延迟"
            body="数据库文件完成一次读或写平均所需的时间。"
            series={[
              {
                name: MSSQL_PRO_NAMES.readLatency,
                label: '读取',
                color: MSSQL_PRO_PALETTE.blue,
                unit: 'ms'
              },
              {
                name: MSSQL_PRO_NAMES.writeLatency,
                label: '写入',
                color: MSSQL_PRO_PALETTE.orange,
                unit: 'ms'
              }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
          <MssqlTrend
            anchor="throughput"
            title="读写吞吐"
            body="数据库文件每秒的读、写次数，反映文件访问繁忙程度。"
            series={[
              {
                name: MSSQL_PRO_NAMES.reads,
                label: '读取',
                color: MSSQL_PRO_PALETTE.blue,
                unit: 'cps'
              },
              {
                name: MSSQL_PRO_NAMES.writes,
                label: '写入',
                color: MSSQL_PRO_PALETTE.emerald,
                unit: 'cps'
              }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
        </div>
      </ProSection>
      <ProSection title="日志与临时库">
        <div className={host.chartGrid2}>
          <MssqlTrend
            anchor="log-flush"
            title="事务日志刷写"
            body="事务日志每秒刷到磁盘的次数，反映日志写入的繁忙程度。"
            series={[{
              name: MSSQL_PRO_NAMES.logFlushes,
              label: '日志刷写',
              color: MSSQL_PRO_PALETTE.cyan,
              unit: 'cps'
            }]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
          <MssqlTrend
            anchor="tempdb"
            title="TempDB 健康"
            body="TempDB 当前可用空间，以及版本存储占用的大小。可用空间持续下降或版本存储持续增大，说明临时对象或长事务压力在升高。"
            holdSeriesColor
            series={[
              {
                name: MSSQL_PRO_NAMES.tempdbFree,
                label: '可用空间',
                color: MSSQL_PRO_PALETTE.emerald,
                unit: 'kibibytes'
              },
              {
                name: MSSQL_PRO_NAMES.versionStore,
                label: '版本存储',
                color: MSSQL_PRO_PALETTE.amber,
                unit: 'kibibytes'
              }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
        </div>
      </ProSection>
      <ProSection title="卷空间">
        <div className="grid w-full min-w-0 grid-cols-1 items-stretch gap-3 min-[1100px]:min-h-[180px] min-[1100px]:grid-cols-[minmax(200px,0.38fr)_minmax(0,1fr)]">
          <section
            id="mssql-volume"
            className={`${classic.panel} ${host.chartPanel} flex h-full min-w-0 flex-col`}
            data-mssql-chart="volume"
            data-mssql-volume={volumeFace === 'loading' ? 'loading' : usage.state}
          >
            <div className={host.chartHead}>
              <div className={host.chartTitle}>
                <span className="inline-flex items-center gap-1">
                  卷空间使用率
                  <MssqlHint kind="mssql-volume" title="卷空间使用率" body={VOLUME_BODY} />
                </span>
              </div>
            </div>
            {volumeFace === 'loading' ? (
              <div className="flex flex-1 items-center justify-center">
                <ProDashLoading />
              </div>
            ) : volumeFace === 'empty' ? (
              <div className={`${host.chartEmpty} ${host.emptyShell}`}>
                <div className="text-[13px] font-semibold text-[var(--color-text-2)]">本窗口暂无数据</div>
              </div>
            ) : (
              <div className="flex flex-1 flex-col justify-center">
                <div
                  className="text-[30px] font-bold leading-none tabular-nums text-[var(--color-text-1)]"
                  data-mssql-volume-reading=""
                >
                  {usage.percent == null ? '—' : formatPercentPoint(usage.percent)}
                </div>
                {note ? (
                  <div className="mt-3 text-[13px] leading-5 text-[var(--color-text-3)]" data-mssql-volume-note="">
                    {note}
                  </div>
                ) : null}
              </div>
            )}
          </section>
          <MssqlTrend
            anchor="volume-trend"
            title="卷空间使用率"
            body={VOLUME_BODY}
            percent
            data={usagePoints}
            series={[{
              name: MSSQL_PRO_NAMES.volumeUsed,
              label: '使用率',
              color: MSSQL_PRO_PALETTE.blue,
              unit: 'percent'
            }]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
            loading={volumeFace === 'loading'}
          />
        </div>
      </ProSection>
      <ProSection title="数据库压力排行">
        <section
          id="mssql-db-rank"
          className={`${classic.panel} ${host.chartPanel}`}
          data-mssql-chart="db-rank"
          data-mssql-rank-layout="all"
        >
          <div className={host.chartHead}>
            <div className={host.chartTitle}>
              <span className="inline-flex items-center gap-1">
                数据库压力排行
                <MssqlHint
                  kind="mssql-db-rank"
                  title="数据库压力排行"
                  body="按数据库同时列出读取延迟、写入延迟和读写繁忙。读写繁忙是每秒次数，不是时长。"
                />
              </span>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 min-[1440px]:grid-cols-3" data-mssql-rank-groups="3">
            {rankGroups.map((group) => (
              <div key={group.key} data-mssql-rank={group.key} data-mssql-face={group.face} className="min-w-0">
                <div className="text-[13px] font-semibold text-[var(--color-text-1)]">{group.label}</div>
                {group.face === 'loading' ? (
                  <div className="flex h-16 items-center justify-center">
                    <ProDashLoading />
                  </div>
                ) : group.face === 'empty' ? (
                  <div className="flex h-16 items-center text-[13px] font-semibold text-[var(--color-text-2)]">
                    本窗口暂无数据
                  </div>
                ) : (
                  <BarList items={group.items} styles={{ ...styles, barsFull: '' }} />
                )}
              </div>
            ))}
          </div>
        </section>
      </ProSection>
    </div>
  );
}
