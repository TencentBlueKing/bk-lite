import React from 'react';
import { Tabs } from 'antd';
import EventLevelTag from '@/components/event-level-tag';

export interface EventDetailHeaderMetaItem {
  key: string;
  label: React.ReactNode;
  value: React.ReactNode;
}

interface EventDetailHeaderProps {
  levelLabel: React.ReactNode;
  levelColor: string;
  title: React.ReactNode;
  metaItems: EventDetailHeaderMetaItem[];
  activeTab: string;
  tabs: { key: string; label: React.ReactNode; children?: React.ReactNode }[];
  onTabChange: (key: string) => void;
}

const EventDetailHeader: React.FC<EventDetailHeaderProps> = ({
  levelLabel,
  levelColor,
  title,
  metaItems,
  activeTab,
  tabs,
  onTabChange,
}) => {
  return (
    <div className="shrink-0">
      <div>
        <EventLevelTag label={levelLabel} color={levelColor} />
        <b>{title}</b>
      </div>
      <ul className="mt-[10px] flex">
        {metaItems.map((item) => (
          <li key={item.key} className="mr-[20px]">
            <span>{item.label}：</span>
            <span>{item.value}</span>
          </li>
        ))}
      </ul>
      <Tabs activeKey={activeTab} items={tabs} onChange={onTabChange} />
    </div>
  );
};

export default EventDetailHeader;
