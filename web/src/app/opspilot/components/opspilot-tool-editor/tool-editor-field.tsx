'use client';

import React from 'react';

export interface ToolEditorFieldProps {
  label: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  labelClassName?: string;
  controlClassName?: string;
}

const joinClassNames = (...values: Array<string | undefined>) =>
  values.filter(Boolean).join(' ');

const ToolEditorField: React.FC<ToolEditorFieldProps> = ({
  label,
  children,
  className,
  labelClassName,
  controlClassName,
}) => {
  return (
    <div className={className}>
      <div
        className={joinClassNames(
          'mb-1 text-sm text-[var(--color-text-2)]',
          labelClassName,
        )}
      >
        {label}
      </div>
      <div className={controlClassName}>{children}</div>
    </div>
  );
};

export default ToolEditorField;
