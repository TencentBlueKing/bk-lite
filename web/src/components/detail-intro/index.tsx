import React from 'react';
import Icon from '@/components/icon';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

export interface DetailIntroProps {
  title?: string | null;
  description?: string | null;
  iconType?: string;
  visual?: React.ReactNode;
  iconSize?: number;
  layout?: 'horizontal' | 'vertical';
  align?: 'start' | 'center';
  className?: string;
  contentClassName?: string;
  titleClassName?: string;
  descriptionClassName?: string;
  titleTruncate?: boolean;
  descriptionTruncate?: boolean;
}

const DetailIntro: React.FC<DetailIntroProps> = ({
  title,
  description,
  iconType,
  visual,
  iconSize = 34,
  layout = 'horizontal',
  align = 'start',
  className = '',
  contentClassName = '',
  titleClassName = '',
  descriptionClassName = '',
  titleTruncate = true,
  descriptionTruncate = true,
}) => {
  const isVertical = layout === 'vertical';
  const isCentered = align === 'center';
  const titleOverflowClassName = titleTruncate
    ? isVertical
      ? 'overflow-hidden text-ellipsis whitespace-nowrap'
      : 'whitespace-nowrap overflow-hidden text-ellipsis'
    : '';
  const descriptionOverflowClassName = descriptionTruncate
    ? 'whitespace-nowrap overflow-hidden text-ellipsis'
    : '';
  const media = visual ?? (
    iconType ? (
      <Icon
        type={iconType}
        style={{ height: `${iconSize}px`, width: `${iconSize}px` }}
      />
    ) : null
  );

  return (
    <div
      className={[
        'flex h-full w-full',
        isVertical ? 'flex-col justify-center' : 'items-center',
        isCentered ? 'items-center text-center' : '',
        className,
      ].join(' ').trim()}
    >
      {media ? (
        <div className={isVertical ? 'mb-[8px] flex justify-center' : 'mr-[10px] flex items-center'}>
          {media}
        </div>
      ) : null}
      <div
        className={[
          isVertical ? 'max-w-full' : 'min-w-0 flex-1 overflow-hidden',
          contentClassName,
        ].join(' ').trim()}
      >
        <EllipsisWithTooltip
          text={title || ''}
          className={[
            isVertical ? 'max-w-full text-center' : '',
            titleOverflowClassName,
            description ? 'mb-2 text-base font-semibold' : '',
            titleClassName,
          ].join(' ').trim()}
        />
        {description ? (
          <EllipsisWithTooltip
            text={description}
            className={[
              'text-xs text-[var(--color-text-3)]',
              descriptionOverflowClassName,
              descriptionClassName,
            ].join(' ').trim()}
          />
        ) : null}
      </div>
    </div>
  );
};

export default DetailIntro;
