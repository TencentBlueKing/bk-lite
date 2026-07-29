import React from 'react';
import { Tag } from 'antd';
import { AlertOutlined } from '@ant-design/icons';

interface EventLevelTagProps {
  label: React.ReactNode;
  color: string;
  withIcon?: boolean;
  icon?: React.ReactNode;
}

const EventLevelTag: React.FC<EventLevelTagProps> = ({
  label,
  color,
  withIcon = true,
  icon,
}) => {
  return (
    <Tag icon={icon ?? (withIcon ? <AlertOutlined /> : undefined)} color={color}>
      {label}
    </Tag>
  );
};

export default EventLevelTag;
