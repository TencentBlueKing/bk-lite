import React, { useMemo } from 'react';
import { Spin } from 'antd';
import OperateFormDrawer from '@/components/operate-form-drawer';
import EventDetailHeader, {
  type EventDetailHeaderMetaItem,
} from './header';
import EventTimelinePanel, {
  type EventTimelineItem,
} from './timeline-panel';
import type { HeatMapCellClickPayload } from './heatMap';

export type { EventDetailHeaderMetaItem } from './header';
export type { EventTimelineItem } from './timeline-panel';

interface EventDetailDrawerProps<T extends EventTimelineItem> {
  visible: boolean;
  title: React.ReactNode;
  headerTitle: React.ReactNode;
  levelLabel: React.ReactNode;
  levelColor: string;
  metaItems: EventDetailHeaderMetaItem[];
  activeTab: string;
  tabs: { key: string; label: React.ReactNode; children?: React.ReactNode }[];
  onTabChange: (key: string) => void;
  onClose: () => void;
  closeLabel: React.ReactNode;
  informationContent: React.ReactNode;
  events: T[];
  renderTimelineContent: (item: T) => React.ReactNode;
  onHeatMapCellClick?: (payload: HeatMapCellClickPayload) => number | void;
  width?: number;
  destroyOnClose?: boolean;
  pageLoading?: boolean;
  informationLoading?: boolean;
  timelineLoading?: boolean;
  extra?: React.ReactNode;
}

const EventDetailDrawer = <T extends EventTimelineItem>({
  visible,
  title,
  headerTitle,
  levelLabel,
  levelColor,
  metaItems,
  activeTab,
  tabs,
  onTabChange,
  onClose,
  closeLabel,
  informationContent,
  events,
  renderTimelineContent,
  onHeatMapCellClick,
  width = 800,
  destroyOnClose,
  pageLoading,
  informationLoading,
  timelineLoading,
  extra,
}: EventDetailDrawerProps<T>) => {
  const isInformation = useMemo(
    () => activeTab === 'information',
    [activeTab]
  );

  return (
    <>
      <OperateFormDrawer
        title={title}
        visible={visible}
        width={width}
        destroyOnClose={destroyOnClose}
        onClose={onClose}
        cancelText={closeLabel}
        onCancel={onClose}
        styles={{
          body: {
            overflow: 'hidden',
            padding: 16,
            display: 'flex',
            flexDirection: 'column',
          },
        }}
      >
        <Spin
          spinning={pageLoading}
          wrapperClassName="flex-1 min-h-0 [&>.ant-spin-container]:h-full"
        >
          <div className="flex h-full flex-col overflow-hidden">
            <EventDetailHeader
              levelLabel={levelLabel}
              levelColor={levelColor}
              title={headerTitle}
              activeTab={activeTab}
              tabs={tabs}
              onTabChange={onTabChange}
              metaItems={metaItems}
            />
            <div
              className={`flex-1 min-h-0 ${
                isInformation ? 'overflow-auto' : 'overflow-hidden'
              }`}
            >
              {isInformation ? (
                <Spin className="w-full" spinning={informationLoading}>
                  {informationContent}
                </Spin>
              ) : (
                <EventTimelinePanel
                  events={events}
                  loading={timelineLoading}
                  onHeatMapCellClick={onHeatMapCellClick}
                  renderTimelineContent={renderTimelineContent}
                />
              )}
            </div>
          </div>
        </Spin>
      </OperateFormDrawer>
      {extra}
    </>
  );
};

export default EventDetailDrawer;
export type { HeatMapCellClickPayload } from './heatMap';
