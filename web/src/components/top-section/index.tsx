import React from 'react';
import Icon from '@/components/icon'
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip'

interface TopSectionProps {
  title: React.ReactNode;
  content: React.ReactNode;
  iconType?: string;
  icon?: React.ReactNode;
  iconSrc?: string;
  iconAlt?: string;
  variant?: string;
  className?: string;
}

const TopSection: React.FC<TopSectionProps> = ({ title, content, iconType, icon }) => (
  <div className="flex h-20 w-full items-center rounded-md bg-(--color-bg) p-4">
    {icon ? (
      <div className="mr-3 flex h-18 w-18 items-center justify-center">{icon}</div>
    ) : iconType ? (
      <div>
        <Icon type={iconType} className="mr-2 text-6xl" />
      </div>
    ) : null}
    <div className="flex-1 overflow-hidden">
      <h2 className="text-base font-semibold mb-2">{title}</h2>
      <EllipsisWithTooltip className="overflow-hidden text-ellipsis whitespace-nowrap text-xs text-(--color-text-3)" text={content} />
    </div>
  </div>
);

export default TopSection;
