import React from 'react';

export interface ToolbarSplitShellProps {
  leading?: React.ReactNode;
  trailing?: React.ReactNode;
  className?: string;
  leadingClassName?: string;
  trailingClassName?: string;
}

const joinClassNames = (...values: Array<string | undefined>) =>
  values.filter(Boolean).join(' ');

const ToolbarSplitShell: React.FC<ToolbarSplitShellProps> = ({
  leading,
  trailing,
  className,
  leadingClassName,
  trailingClassName,
}) => {
  const justifyClassName = leading && trailing
    ? 'justify-between'
    : trailing
      ? 'justify-end'
      : 'justify-start';

  return (
    <div
      className={joinClassNames(
        'mb-4 flex flex-wrap items-center gap-x-4 gap-y-3',
        justifyClassName,
        className,
      )}
    >
      {leading ? (
        <div
          className={joinClassNames(
            'flex min-w-0 flex-wrap items-center gap-3',
            leadingClassName,
          )}
        >
          {leading}
        </div>
      ) : null}
      {trailing ? (
        <div
          className={joinClassNames(
            'flex flex-wrap items-center justify-end gap-2',
            trailingClassName,
          )}
        >
          {trailing}
        </div>
      ) : null}
    </div>
  );
};

export default ToolbarSplitShell;
