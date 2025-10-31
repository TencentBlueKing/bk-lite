import React, { useState, useEffect, useCallback, memo, useMemo } from 'react';
import { Tooltip as Tip } from 'antd';
import { useFormatTime } from '@/app/monitor/utils/common';
import { TableDataItem } from '@/app/monitor/types';
import { LEVEL_MAP } from '@/app/monitor/constants';
import { isNumber } from 'lodash';

interface EventBarProps {
  eventData: TableDataItem[];
  minTime: number;
  maxTime: number;
}

const EventBar: React.FC<EventBarProps> = memo(
  ({ eventData, minTime, maxTime }) => {
    const { formatTime } = useFormatTime();
    const [boxItems, setBoxItems] = useState<TableDataItem[]>([]);

    const timeRange = useMemo(
      () => ({
        isSinglePoint: maxTime === minTime,
        intervals:
          maxTime === minTime ? 120 : Math.ceil((maxTime - minTime) / 60),
      }),
      [maxTime, minTime]
    );

    const displayConfig = useMemo(
      () => ({
        lengths:
          timeRange.intervals >= 120 ? 24 : Math.ceil(timeRange.intervals / 5),
        step: Math.ceil(
          eventData.length /
            (timeRange.intervals >= 120
              ? 24
              : Math.ceil(timeRange.intervals / 5))
        ),
      }),
      [timeRange.intervals, eventData.length]
    );

    const timeToSecond = useCallback((time: string) => {
      return Math.floor(new Date(time).getTime() / 1000);
    }, []);

    const cutArray = useCallback(
      (array: TableDataItem[], subLength: number) => {
        let index = 0;
        const newArr = [];
        while (index < array.length) {
          newArr.push(array.slice(index, (index += subLength)));
        }
        return newArr;
      },
      []
    );

    const handleCutArray = useCallback(
      (array: TableDataItem[]) => {
        if (!array) return [];
        const test = array.map((item) => {
          return item
            .sort((prev: TableDataItem, next: TableDataItem) => {
              let flag = null;
              if (prev.value > next.value) {
                flag = 1;
              } else if (prev.value < next.value) {
                flag = -1;
              } else {
                flag =
                  timeToSecond(prev.created_at) > timeToSecond(next.created_at)
                    ? 1
                    : -1;
              }
              return flag;
            })
            .pop();
        });
        return test;
      },
      [timeToSecond]
    );

    const processEventData = useCallback(() => {
      if (!eventData.length) {
        setBoxItems([]);
        return;
      }

      const time_intervals: TableDataItem[] = timeRange.isSinglePoint
        ? eventData
        : eventData.filter((item: any) => {
          const times = timeToSecond(item.created_at);
          return times >= minTime && times <= maxTime;
        });

      setBoxItems(
        handleCutArray(cutArray(time_intervals.reverse(), displayConfig.step))
      );
    }, [
      eventData,
      minTime,
      maxTime,
      timeRange.isSinglePoint,
      timeToSecond,
      handleCutArray,
      cutArray,
      displayConfig.step,
    ]);

    useEffect(() => {
      if (eventData.length > 0) {
        processEventData();
      }
    }, [eventData, minTime, maxTime, processEventData]);

    if (!eventData?.length || !boxItems?.length) {
      return null;
    }

    return (
      <div className="flex w-[100%] pl-14 pr-[15px] justify-between">
        {boxItems?.map((item, index) => {
          return (
            <Tip
              key={index}
              title={`${formatTime(
                Date.parse(item.created_at) / 1000,
                minTime,
                maxTime
              )} ${isNumber(item.value) ? item.value.toFixed(2) : item.value}`}
            >
              <span
                className="flex-1 mr-1 h-2"
                style={{
                  backgroundColor: LEVEL_MAP[item.level] as string,
                }}
              ></span>
            </Tip>
          );
        })}
      </div>
    );
  }
);

EventBar.displayName = 'EventBar';

export default EventBar;
