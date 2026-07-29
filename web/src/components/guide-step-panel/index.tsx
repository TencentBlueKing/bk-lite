import React from 'react';

export interface GuideStepPanelProps {
  step: React.ReactNode;
  title: React.ReactNode;
  children: React.ReactNode;
  description?: React.ReactNode;
  eyebrow?: React.ReactNode;
  variant?: 'card' | 'timeline';
  spacing?: 'default' | 'flush';
  showConnector?: boolean;
  className?: string;
  cardClassName?: string;
  headerClassName?: string;
  bodyClassName?: string;
  connectorClassName?: string;
  stepBadgeClassName?: string;
  titleClassName?: string;
  descriptionClassName?: string;
  eyebrowClassName?: string;
}

const joinClassName = (...values: Array<string | undefined>) =>
  values.filter(Boolean).join(' ');

const GuideStepPanel: React.FC<GuideStepPanelProps> = ({
  step,
  title,
  children,
  description,
  eyebrow,
  variant = 'card',
  spacing = 'default',
  showConnector = false,
  className,
  cardClassName,
  headerClassName,
  bodyClassName,
  connectorClassName,
  stepBadgeClassName,
  titleClassName,
  descriptionClassName,
  eyebrowClassName,
}) => {
  const spacingClassName = spacing === 'flush' ? 'mb-0' : 'mb-[24px]';

  if (variant === 'timeline') {
    return (
      <div className={joinClassName('relative pl-12 md:pl-14', className)}>
        <div className="absolute left-0 top-0 flex h-full w-12 justify-center md:w-14">
          {showConnector ? (
            <div
              className={joinClassName(
                'absolute left-[19px] top-10 bottom-0 w-px bg-[linear-gradient(to_bottom,var(--color-border-3),color-mix(in_srgb,var(--color-border-1)_55%,transparent))] md:left-[23px]',
                connectorClassName,
              )}
            />
          ) : null}
          <div
            className={joinClassName(
              'relative z-10 flex h-8 w-8 items-center justify-center rounded-full border border-[var(--color-border-2)] bg-[var(--color-fill-1)] text-[12px] font-semibold text-[var(--color-primary)]',
              stepBadgeClassName,
            )}
          >
            {step}
          </div>
        </div>

        <div
          className={joinClassName(
            'rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-5 py-5 sm:px-6',
            cardClassName,
          )}
        >
          {eyebrow ? (
            <div className={joinClassName('flex flex-wrap items-center gap-x-3 gap-y-2', headerClassName)}>
              <div
                className={joinClassName(
                  'text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--color-text-3)]',
                  eyebrowClassName,
                )}
              >
                {eyebrow}
              </div>
              <div className="h-px min-w-[72px] flex-1 bg-[var(--color-border-1)]" />
            </div>
          ) : null}
          <div
            className={joinClassName(
              eyebrow ? 'mt-3' : '',
              'text-[18px] font-semibold leading-7 text-[var(--color-text-1)]',
              titleClassName,
            )}
          >
            {title}
          </div>
          {description ? (
            <div
              className={joinClassName(
                'mt-1.5 max-w-[760px] text-[13px] leading-6 text-[var(--color-text-2)]',
                descriptionClassName,
              )}
            >
              {description}
            </div>
          ) : null}
          <div className={joinClassName('mt-5', bodyClassName)}>{children}</div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={joinClassName(
        spacingClassName,
        'rounded-[8px] bg-[var(--color-fill-1)] p-[16px]',
        className,
      )}
    >
      <div className={joinClassName('mb-[16px] flex items-center gap-2', headerClassName)}>
        <div
          className={joinClassName(
            'flex h-[24px] w-[24px] items-center justify-center rounded-full bg-[var(--color-primary)] text-[14px] font-medium text-white',
            stepBadgeClassName,
          )}
        >
          {step}
        </div>
        <span
          className={joinClassName(
            'text-[14px] font-medium text-[var(--color-text-1)]',
            titleClassName,
          )}
        >
          {title}
        </span>
      </div>
      <div className={joinClassName('ml-[32px]', bodyClassName)}>
        {description ? (
          <div
            className={joinClassName(
              'mb-[12px] text-[12px] text-[var(--color-text-3)]',
              descriptionClassName,
            )}
          >
            {description}
          </div>
        ) : null}
        {children}
      </div>
    </div>
  );
};

export default GuideStepPanel;
