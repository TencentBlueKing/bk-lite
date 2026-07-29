import React from 'react';

export interface FilterToolbarProps {
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
  align?: 'start' | 'end' | 'between';
  spacing?: 'default' | 'flush';
}

const joinClassNames = (...values: Array<string | undefined>) =>
  values.filter(Boolean).join(' ');

const FilterToolbar: React.FC<FilterToolbarProps> = ({
  children,
  className,
  contentClassName,
  align = 'end',
  spacing = 'default',
}) => {
  const outerAlignmentClassName =
    align === 'start' ? 'justify-start' : 'justify-end';
  const innerAlignmentClassName =
    align === 'between'
      ? 'w-full justify-between'
      : align === 'start'
        ? 'justify-start'
        : 'justify-end';
  const spacingClassName = spacing === 'flush' ? 'mb-0' : 'mb-3';

  return (
    <div
      className={joinClassNames(
        `${spacingClassName} flex flex-none`,
        outerAlignmentClassName,
        className,
      )}
    >
      <div
        className={joinClassNames(
          'flex flex-wrap items-center gap-3',
          innerAlignmentClassName,
          contentClassName,
        )}
      >
        {children}
      </div>
    </div>
  );
};

export default FilterToolbar;
