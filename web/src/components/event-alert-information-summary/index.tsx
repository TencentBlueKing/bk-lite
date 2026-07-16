import React from 'react';
import { Descriptions } from 'antd';

export interface EventAlertInformationSummaryItem {
  key: React.Key;
  label: React.ReactNode;
  value: React.ReactNode;
  span?: number;
  hidden?: boolean;
}

interface EventAlertInformationSummaryProps {
  title: React.ReactNode;
  items: EventAlertInformationSummaryItem[];
  actions?: React.ReactNode;
  className?: string;
  actionsClassName?: string;
}

const EventAlertInformationSummary: React.FC<
  EventAlertInformationSummaryProps
> = ({
  title,
  items,
  actions,
  className,
  actionsClassName = 'mt-4',
}) => {
  return (
    <div className={className}>
      <Descriptions title={title} column={2} bordered>
        {items
          .filter((item) => !item.hidden)
          .map((item) => (
            <Descriptions.Item
              key={item.key}
              label={item.label}
              span={item.span}
            >
              {item.value}
            </Descriptions.Item>
          ))}
      </Descriptions>
      {actions ? <div className={actionsClassName}>{actions}</div> : null}
    </div>
  );
};

export default EventAlertInformationSummary;
