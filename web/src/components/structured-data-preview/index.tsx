'use client';

import type { CSSProperties, ReactNode } from 'react';

export interface StructuredDataPreviewProps {
  value?: unknown;
  empty?: ReactNode;
  className?: string;
  maxHeight?: CSSProperties['maxHeight'];
}

const joinClassName = (...values: Array<string | undefined>) =>
  values.filter(Boolean).join(' ');

const stringifyValue = (value: unknown) => {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

export default function StructuredDataPreview({
  value,
  empty = '--',
  className,
  maxHeight = '14rem',
}: StructuredDataPreviewProps) {
  if (value === undefined || value === null || value === '') {
    return <div className="text-xs text-(--color-text-3)">{empty}</div>;
  }

  const sharedClassName = joinClassName(
    'overflow-auto rounded-lg bg-(--color-fill-1) p-3 text-xs leading-5 text-(--color-text-2)',
    className,
  );
  const style = { maxHeight };

  if (typeof value === 'string') {
    return (
      <div className={joinClassName(sharedClassName, 'whitespace-pre-wrap break-all')} style={style}>
        {value}
      </div>
    );
  }

  return (
    <pre className={joinClassName(sharedClassName, 'm-0 whitespace-pre-wrap break-all')} style={style}>
      {stringifyValue(value)}
    </pre>
  );
}
