import type { CSSProperties } from 'react';

export interface HttpMethodBadgeProps {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH' | string;
  className?: string;
  style?: CSSProperties;
}

const STYLE_BY_METHOD: Record<string, { backgroundColor: string; color: string }> = {
  GET: {
    backgroundColor: 'var(--color-primary)',
    color: '#ffffff',
  },
  POST: {
    backgroundColor: 'var(--color-success)',
    color: '#ffffff',
  },
  PUT: {
    backgroundColor: 'var(--color-warning)',
    color: '#ffffff',
  },
  DELETE: {
    backgroundColor: 'var(--color-fail)',
    color: '#ffffff',
  },
  PATCH: {
    backgroundColor: '#722ed1',
    color: '#ffffff',
  },
};

const HttpMethodBadge = ({
  method,
  className,
  style,
}: HttpMethodBadgeProps) => {
  const normalizedMethod = (method || 'GET').toUpperCase();
  const palette = STYLE_BY_METHOD[normalizedMethod] || STYLE_BY_METHOD.GET;

  return (
    <span
      className={[
        'inline-flex w-[52px] shrink-0 items-center justify-center rounded px-2 py-0.5 font-mono text-[11px] font-semibold leading-4 tracking-wide select-none',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      style={{
        backgroundColor: palette.backgroundColor,
        color: palette.color,
        ...style,
      }}
    >
      {normalizedMethod}
    </span>
  );
};

export default HttpMethodBadge;
