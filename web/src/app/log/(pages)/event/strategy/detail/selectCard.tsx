import React from 'react';
import { Tag } from 'antd';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import { CardItem, SelectCardProps } from '@/app/log/types/event';

// 根据 channel_type 返回对应的 Tag 显示文本的翻译键
const getChannelTypeKey = (channelType: string): string => {
  const keyMap: Record<string, string> = {
    email: 'log.event.channelTypeEmail',
    enterprise_wechat_bot: 'log.event.channelTypeWechatBot'
  };
  return keyMap[channelType] || '';
};

// 根据 CSS 变量生成带透明度的颜色
const getColorWithOpacity = (cssVar: string, opacity: number): string => {
  return `color-mix(in srgb, var(${cssVar}) ${opacity * 100}%, transparent)`;
};

const SelectCard: React.FC<SelectCardProps> = ({
  data = [],
  value,
  onChange,
  cardWidth
}) => {
  const { t } = useTranslation();

  const handleCardClick = (item: CardItem) => {
    onChange?.(item.value);
  };

  return (
    <div
      className={cardWidth ? 'grid gap-4' : 'grid grid-cols-3 gap-4'}
      style={{
        gridAutoRows: '1fr',
        ...(cardWidth
          ? { gridTemplateColumns: `repeat(auto-fill, ${cardWidth}px)` }
          : {})
      }}
    >
      {data.map((item, index) => {
        const isSelected = value === item.value;
        const tagKey = item.tag ? getChannelTypeKey(item.tag) : '';
        return (
          <div
            key={index}
            onClick={() => handleCardClick(item)}
            style={{
              width: cardWidth ? `${cardWidth}px` : undefined,
              backgroundColor: isSelected
                ? getColorWithOpacity('--color-primary', 0.04)
                : undefined
            }}
            className={`bg-[var(--color-bg-1)] border-2 ${
              isSelected
                ? 'border-[var(--color-primary)] shadow-[0_8px_24px_rgba(0,112,243,0.2)]'
                : 'border-transparent'
            } shadow-md transition-all duration-300 ease-in-out rounded-lg p-3 cursor-pointer group hover:shadow-lg`}
          >
            <div className="flex gap-3 h-full">
              {/* 左侧图标 */}
              {item.icon && (
                <Icon
                  type={item.icon}
                  className="text-2xl flex-shrink-0 mt-1"
                />
              )}
              {/* 右侧内容 */}
              <div className="flex-1 min-w-0 flex flex-col">
                <h2
                  className="text-[14px] font-bold m-0 truncate"
                  title={item.title}
                >
                  {item.title}
                </h2>
                {item.tag && (
                  <div className="mt-1">
                    <Tag color="blue" className="text-[12px]">
                      {tagKey ? t(tagKey) : item.tag}
                    </Tag>
                  </div>
                )}
                <p
                  className="text-[var(--color-text-3)] text-[12px] m-0 mt-1 line-clamp-2 flex-1"
                  title={item.description || '--'}
                >
                  {item.description || '--'}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default SelectCard;
