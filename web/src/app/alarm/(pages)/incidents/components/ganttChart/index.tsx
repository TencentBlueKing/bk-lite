'use client';

import { useMemo, useRef } from 'react';
import dayjs from 'dayjs';
import minMax from 'dayjs/plugin/minMax';
import styles from './index.module.scss';
import AlertDetail from '../../../alarms/components/alarmDetail';
import { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import { ModalRef } from '@/app/alarm/types/types';
import { Tooltip, Checkbox, Spin } from 'antd';
import { useCommon } from '@/app/alarm/context/common';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
dayjs.extend(minMax);

interface GanttChartProps {
  loading?: boolean;
  alarmData: AlarmTableDataItem[];
  selectedTasks: number[];
  onSelectionChange: (keys: number[]) => void;
}

export default function GanttChart({
  loading,
  alarmData = [],
  selectedTasks,
  onSelectionChange,
}: GanttChartProps) {
  const detailRef = useRef<ModalRef>(null);
  const { levelMap } = useCommon();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { t } = useTranslation();

  const toggleTask = (id: number) => {
    const next = selectedTasks.includes(id)
      ? selectedTasks.filter((x) => x !== id)
      : [...selectedTasks, id];
    onSelectionChange(next);
  };

  const times = useMemo(() => {
    const starts = alarmData.map((d) => dayjs(d.first_event_time));
    const ends = alarmData.map((d) => dayjs(d.last_event_time || d.first_event_time));
    let min = dayjs.min(...starts) || dayjs();
    let max = dayjs.max(...ends) || dayjs();
    if (!min.isValid()) min = dayjs();
    if (!max.isValid() || max.isBefore(min)) max = min;
    // 同一时刻的告警没有跨度，时间轴会叠成一个点，左右各留半小时才能拉开。
    if (max.diff(min) < 60 * 1000) {
      min = min.subtract(30, 'minute');
      max = max.add(30, 'minute');
    }
    return { min, max, total: Math.max(max.diff(min), 1) };
  }, [alarmData]);

  const ticks = useMemo(() => {
    const totalMs = times.total;
    const minTicks = 6;
    const count = Math.max(minTicks, minTicks);
    const intervalMs = totalMs / count;
    return Array.from({ length: count + 1 }).map((_, i) => {
      const tm = dayjs(times.min.valueOf() + intervalMs * i);
      const left = (tm.diff(times.min) / totalMs) * 100;
      return { label: tm.format('MM-DD HH:mm'), left };
    });
  }, [times]);

  const onOpenDetail = (task: any) => {
    detailRef.current?.showModal({
      title: task.title,
      type: 'add',
      form: task,
    });
  };

  const sortedData = useMemo(
    () =>
      [...alarmData].sort(
        (a: any, b: any) =>
          new Date(a.first_event_time).getTime() -
          new Date(b.first_event_time).getTime()
      ),
    [alarmData]
  );

  return (
    <>
      <div className={styles.chartWrapper}>
        <Spin spinning={loading} wrapperClassName={styles.spin}>
          {!sortedData?.length ? (
            <CompactEmptyState description={t('common.noData')} />
          ) : (
            <div className={styles.chartGrid}>
              <div className={styles.axisRow}>
                <div className={styles.gutter} />
                <div className={styles.axis}>
                  {ticks.map((tick, idx) => (
                    <span
                      key={idx}
                      className={styles.axisTick}
                      style={{
                        left: `${tick.left}%`,
                        transform: tick.left < 8
                          ? 'translateX(0)'
                          : tick.left > 92
                            ? 'translateX(-100%)'
                            : 'translateX(-50%)',
                      }}
                    >
                      {tick.label}
                    </span>
                  ))}
                </div>
              </div>
              <div className={styles.chartContent}>
                <div className={styles.lines} aria-hidden="true">
                  {ticks.map((tick, idx) => (
                    <div
                      key={`full-line-${idx}`}
                      className={styles.axisLine}
                      style={{ left: `${tick.left}%` }}
                    />
                  ))}
                </div>
                {sortedData.map((d) => {
                  const s = dayjs(d.first_event_time).diff(times.min);
                  const w = dayjs(d.last_event_time || d.first_event_time).diff(
                    dayjs(d.first_event_time)
                  );
                  const rawLeft = (s / times.total) * 100;
                  const clampedLeft = Math.min(Math.max(rawLeft, 0), 100);
                  const rawWidth = (w / times.total) * 100;
                  const clampedWidth = Math.min(
                    Math.max(rawWidth, 0),
                    100 - clampedLeft
                  );
                  const wideBar = clampedWidth >= 12;
                  const titleOnRight = clampedLeft + clampedWidth < 65;

                  return (
                    <div key={d.id} className={styles.alarmRow}>
                      <Checkbox
                        className={styles.alarmCheckbox}
                        checked={selectedTasks.includes(d.id)}
                        onChange={() => toggleTask(d.id)}
                      />
                      <div className={styles.plot}>
                        <Tooltip
                          placement={
                            clampedLeft > 60
                              ? 'topRight'
                              : clampedLeft < 10
                                ? 'topLeft'
                                : 'top'
                          }
                          styles={{
                            body: { width: '300px' },
                          }}
                          title={
                            <>
                              <div>{d.title}</div>
                              <div>
                                {t('alarms.firstEventTime')}:{' '}
                                {d.first_event_time ? convertToLocalizedTime(d.first_event_time) : '--'}
                              </div>
                              <div>
                                {t('alarms.lastEventTime')}:{' '}
                                {d.last_event_time ? convertToLocalizedTime(d.last_event_time) : '--'}
                              </div>
                              <div>
                                {t('alarmCommon.operator')}:{' '}
                                {d.operator_user || '--'}
                              </div>
                            </>
                          }
                        >
                          <div
                            className={styles.bar}
                            style={{
                              left: `${Math.min(clampedLeft, 99)}%`,
                              width: `${clampedWidth}%`,
                              backgroundColor: levelMap[d.level] as string,
                            }}
                            onClick={() => onOpenDetail(d)}
                          >
                            <div
                              className={styles.title}
                              style={wideBar
                                ? { left: '8px' }
                                : titleOnRight
                                  ? { left: 'calc(100% + 8px)' }
                                  : { right: 'calc(100% + 8px)' }}
                            >
                              {d.title}
                            </div>
                          </div>
                        </Tooltip>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </Spin>
        <AlertDetail ref={detailRef} />
      </div>
    </>
  );
}
