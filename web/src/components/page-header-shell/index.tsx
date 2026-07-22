import React from 'react';

export interface PageHeaderShellProps {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  leading?: React.ReactNode;
  subtitleLeading?: React.ReactNode;
  actions?: React.ReactNode;
  as?: 'div' | 'h1' | 'h2' | 'h3';
  className?: string;
  style?: React.CSSProperties;
  headerRowClassName?: string;
  contentClassName?: string;
  titleRowClassName?: string;
  titleClassName?: string;
  subtitleRowClassName?: string;
  subtitleClassName?: string;
  actionsClassName?: string;
}

const PageHeaderShell: React.FC<PageHeaderShellProps> = ({
  title,
  subtitle,
  leading,
  subtitleLeading,
  actions,
  as = 'h2',
  className,
  style,
  headerRowClassName = 'flex items-start justify-between gap-4',
  contentClassName = 'min-w-0',
  titleRowClassName = 'flex items-center gap-2',
  titleClassName = 'm-0 text-base font-medium text-[var(--color-text-1)]',
  subtitleRowClassName = 'mt-1 flex items-start gap-2',
  subtitleClassName = 'm-0 text-sm text-[var(--color-text-3)]',
  actionsClassName,
}) => {
  const TitleTag = as;
  const hasTitleRow = Boolean(title || leading);
  const hasContent = Boolean(hasTitleRow || subtitle);

  return (
    <div className={className} style={style}>
      <div className={headerRowClassName}>
        {hasContent ? (
          <div className={contentClassName}>
            {hasTitleRow ? (
              <div className={titleRowClassName}>
                {leading ? <span className="inline-flex shrink-0">{leading}</span> : null}
                {title ? <TitleTag className={titleClassName}>{title}</TitleTag> : null}
              </div>
            ) : null}
            {subtitle ? (
              <div className={subtitleRowClassName}>
                {subtitleLeading ? (
                  <span className="inline-flex shrink-0" aria-hidden="true">
                    {subtitleLeading}
                  </span>
                ) : null}
                <p className={subtitleClassName}>{subtitle}</p>
              </div>
            ) : null}
          </div>
        ) : null}
        {actions ? <div className={actionsClassName}>{actions}</div> : null}
      </div>
    </div>
  );
};

export default PageHeaderShell;
