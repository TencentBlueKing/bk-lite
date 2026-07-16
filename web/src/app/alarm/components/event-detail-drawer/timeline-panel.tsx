import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Spin } from 'antd';
import VirtualList from 'rc-virtual-list';
import type { ListRef } from 'rc-virtual-list';
import type { HeatMapDataItem } from '@/types';
import EventHeatMap, {
  getHeatMapCellColor,
  type HeatMapCellClickPayload,
} from './heatMap';

const TIMELINE_ITEM_HEIGHT = 48;

export interface EventTimelineItem extends HeatMapDataItem {
  id?: React.Key;
  content?: React.ReactNode;
}

interface EventTimelinePanelProps<T extends EventTimelineItem> {
  events: T[];
  loading?: boolean;
  onHeatMapCellClick?: (payload: HeatMapCellClickPayload) => number | void;
  renderTimelineContent: (item: T) => React.ReactNode;
}

const EventTimelinePanel = <T extends EventTimelineItem>({
  events,
  loading,
  onHeatMapCellClick,
  renderTimelineContent,
}: EventTimelinePanelProps<T>) => {
  const timelineRef = useRef<ListRef | null>(null);
  const timelineContainerRef = useRef<HTMLDivElement | null>(null);
  const [timelineHeight, setTimelineHeight] = useState(200);

  useEffect(() => {
    const container = timelineContainerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const height = Math.floor(entry.contentRect.height);
        if (height > 0) setTimelineHeight(height);
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const eventDotColors = useMemo(() => {
    const hourCountMap = new Map<string, number>();
    events.forEach((item) => {
      if (!item.event_time) return;
      const date = new Date(item.event_time);
      const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}-${date.getHours()}`;
      hourCountMap.set(key, (hourCountMap.get(key) || 0) + 1);
    });

    return events.map((item) => {
      if (!item.event_time) return '#d9d9d9';
      const date = new Date(item.event_time);
      const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}-${date.getHours()}`;
      const count = hourCountMap.get(key) || 0;
      return getHeatMapCellColor(count, 'day');
    });
  }, [events]);

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0">
        <Spin spinning={loading}>
          <EventHeatMap
            data={events}
            className="mb-4"
            onCellClick={(payload) => {
              const targetIndex = onHeatMapCellClick?.(payload);
              if (typeof targetIndex === 'number' && targetIndex >= 0) {
                timelineRef.current?.scrollTo({ index: targetIndex, align: 'top' });
              }
            }}
          />
        </Spin>
      </div>
      <div
        ref={timelineContainerRef}
        className="flex-1 min-h-0 overflow-hidden pl-[4px] pt-[10px]"
      >
        <Spin spinning={loading}>
          <VirtualList
            ref={timelineRef}
            data={events}
            height={timelineHeight - 10}
            itemHeight={TIMELINE_ITEM_HEIGHT}
            itemKey={(item) => item.id || item.event_time || String(item.content)}
          >
            {(item: T, index: number, props: { style: React.CSSProperties }) => {
              const dotColor = eventDotColors[index] || '#d9d9d9';
              const isLast = index === events.length - 1;
              return (
                <div style={props.style} className="relative">
                  {!isLast ? (
                    <div
                      className="absolute"
                      style={{
                        insetInlineStart: 7,
                        top: 16,
                        bottom: 0,
                        width: 2,
                        background: 'rgba(5, 5, 5, 0.06)',
                      }}
                    />
                  ) : null}
                  <div
                    style={{
                      position: 'absolute',
                      width: 10,
                      height: 10,
                      top: 6,
                      insetInlineStart: 3,
                      borderRadius: '50%',
                      border: `3px solid ${dotColor}`,
                      backgroundColor: '#fff',
                      boxSizing: 'border-box',
                    }}
                  />
                  <div
                    style={{
                      marginInlineStart: 26,
                      paddingBottom: isLast ? 0 : 20,
                      wordBreak: 'break-word',
                      fontSize: 14,
                      lineHeight: '22px',
                    }}
                  >
                    {renderTimelineContent(item)}
                  </div>
                </div>
              );
            }}
          </VirtualList>
        </Spin>
      </div>
    </div>
  );
};

export default EventTimelinePanel;
