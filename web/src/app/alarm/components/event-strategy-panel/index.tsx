import type { CSSProperties, ReactNode } from 'react';
import SectionHeader from '@/components/section-header';

interface EventStrategyPanelProps {
  title?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  stickyTop?: number;
  className?: string;
  bodyClassName?: string;
  withShadow?: boolean;
  style?: CSSProperties;
}

const EventStrategyPanel = ({
  title,
  extra,
  children,
  stickyTop,
  className = '',
  bodyClassName = '',
  withShadow = true,
  style,
}: EventStrategyPanelProps) => {
  const rootClassName = [
    'w-full rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-4',
    withShadow ? 'shadow-md' : '',
    stickyTop !== undefined ? 'sticky h-fit self-start transition-[top] duration-150' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={rootClassName}
      style={{ ...style, ...(stickyTop !== undefined ? { top: stickyTop } : {}) }}
    >
      {(title || extra) ? (
        <SectionHeader
          className="mb-3"
          title={title ?? null}
          actions={extra}
          titleClassName="m-0 text-[14px] font-medium text-[var(--color-text-1)]"
          actionsClassName="flex items-center gap-2"
        />
      ) : null}
      <div className={bodyClassName}>{children}</div>
    </div>
  );
};

export default EventStrategyPanel;
