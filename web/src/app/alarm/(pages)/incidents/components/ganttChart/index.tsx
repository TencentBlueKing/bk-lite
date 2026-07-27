'use client';

import React, { useMemo, useRef } from 'react';
import dayjs from 'dayjs';
import minMax from 'dayjs/plugin/minMax';
import styles from './index.module.scss';
import AlertDetail from '../../../alarms/components/alarmDetail';
import { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import { ModalRef } from '@/app/alarm/types/types';
import { Tooltip, Checkbox, Spin } from 'antd';
import { useCommon } from '@/app/alarm/context/common';
import { Empty } from 'antd';
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
    const ends = alarmData.map((d) => dayjs(d.last_event_time));
    const min = dayjs.min(...starts) || dayjs();
    const max = dayjs.max(...ends) || dayjs();
    const total = max.diff(min);
    return { min, max, total };
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
        <Spin spinning={loading}>
          {!sortedData?.length ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('common.noData')}
            />
          ) : (
            <div className={styles.chartGrid}>
              <div className={styles.emptyHeader} />
              <div className={styles.axis}>
                {ticks.map((t, idx) => (
                  <React.Fragment key={idx}>
                    <span
                      className={styles.axisTick}
                      style={{ left: `${t.left}%` }}
                    >
                      {t.label}
                    </span>
                  </React.Fragment>
                ))}
              </div>
              <div>
                {ticks.map((t, idx) => (
                  <div
                    key={`full-line-${idx}`}
                    className={styles.axisLine}
                    style={{ left: `${t.left}%` }}
                  />
                ))}
              </div>
              <div className={styles.chartContent}>
                {sortedData.map((d) => {
                  const s = dayjs(d.first_event_time).diff(times.min);
                  const w = dayjs(d.last_event_time).diff(
                    dayjs(d.first_event_time)
                  );
                  // 防止 total 为 0 并限制 0–100%
                  const rawLeft = times.total > 0 ? (s / times.total) * 100 : 0;
                  const clampedLeft = Math.min(Math.max(rawLeft, 0), 100);
                  const rawWidth =
                    times.total > 0 ? (w / times.total) * 100 : 0;
                  const clampedWidth = Math.min(
                    Math.max(rawWidth, 0),
                    100 - clampedLeft
                  );

                  return (
                    <div key={d.id} className={styles.alarmRow}>
                      <Checkbox
                        className={styles.alarmCheckbox}
                        checked={selectedTasks.includes(d.id)}
                        onChange={() => toggleTask(d.id)}
                      />
                      <div className={styles.barContainer}>
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
                              style={{
                                [clampedLeft < 50 ? 'left' : 'right']:
                                  clampedLeft < 50 ? '8px' : 'calc(100% + 2px)',
                              }}
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
