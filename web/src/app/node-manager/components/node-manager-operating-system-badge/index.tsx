import type { CSSProperties } from 'react';
import { Tooltip, Tag } from 'antd';
import Icon from '@/components/icon';

export interface NodeManagerOperatingSystemBadgeProps {
  operatingSystem?: string | null;
  label?: string | null;
  variant?: 'icon' | 'tag';
  tooltip?: string | null;
  color?: string;
  bordered?: boolean;
  className?: string;
  iconClassName?: string;
  iconStyle?: CSSProperties;
}

const NodeManagerOperatingSystemBadge = ({
  operatingSystem,
  label,
  variant = 'tag',
  tooltip,
  color = 'blue',
  bordered = false,
  className = '',
  iconClassName = '',
  iconStyle,
}: NodeManagerOperatingSystemBadgeProps) => {
  if (!operatingSystem) {
    return null;
  }

  const icon = (
    <Icon
      type={operatingSystem === 'linux' ? 'Linux' : 'Window-Windows'}
      className={iconClassName}
      style={iconStyle}
    />
  );

  const content = variant === 'icon' ? (
    <div className={className}>{icon}</div>
  ) : (
    <Tag color={color} bordered={bordered} className={className} icon={icon}>
      {label || operatingSystem}
    </Tag>
  );

  return tooltip ? <Tooltip title={tooltip}>{content}</Tooltip> : content;
};

export default NodeManagerOperatingSystemBadge;
