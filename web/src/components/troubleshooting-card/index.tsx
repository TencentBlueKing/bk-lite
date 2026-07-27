import React from 'react';

export interface TroubleshootingCardProps {
  badge?: React.ReactNode;
  title: React.ReactNode;
  titleClassName?: string;
  causeLabel?: React.ReactNode;
  cause?: React.ReactNode;
  causes?: React.ReactNode[];
  causeLayout?: 'inline' | 'stacked';
  solutionLabel?: React.ReactNode;
  solutions?: React.ReactNode[];
  className?: string;
  cardClassName?: string;
  solutionTone?: 'default' | 'accent';
}

const baseCardClassName =
  'rounded-[16px] bg-[var(--color-fill-1)] p-4';

const listClassName =
  'mt-2 space-y-2 text-[12px] leading-5 text-[var(--color-text-2)]';

const sectionLabelClassName =
  'text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-text-3)]';

const TroubleshootingCard: React.FC<TroubleshootingCardProps> = ({
  badge,
  title,
  titleClassName = 'text-[13px] font-semibold leading-6 text-[var(--color-text-1)]',
  causeLabel,
  cause,
  causes = [],
  causeLayout = 'stacked',
  solutionLabel,
  solutions = [],
  className = '',
  cardClassName = '',
  solutionTone = 'default',
}) => {
  const mergedCardClassName = [baseCardClassName, cardClassName]
    .filter(Boolean)
    .join(' ');

  const solutionContainerClassName = solutionTone === 'accent'
    ? 'mt-3 rounded-[14px] border border-[color-mix(in_srgb,var(--color-primary)_14%,var(--color-bg-1))] bg-[color-mix(in_srgb,var(--color-primary)_6%,var(--color-bg-1))] px-3.5 py-3'
    : 'mt-3';

  const solutionLabelClassName = solutionTone === 'accent'
    ? 'text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-primary)]'
    : sectionLabelClassName;

  const solutionBulletClassName = solutionTone === 'accent'
    ? 'mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]'
    : 'mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-text-3)]';

  return (
    <div className={className}>
      <div className={mergedCardClassName}>
        <div className="flex items-start gap-3">
          {badge ? (
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)] text-sm font-bold text-white">
              {badge}
            </div>
          ) : null}
          <div className="min-w-0 flex-1">
            <div className={titleClassName}>{title}</div>

            {causeLabel && (cause || causes.length) ? (
              <div className="mt-2">
                {cause && causeLayout === 'inline' ? (
                  <div className="text-sm text-[var(--color-text-3)]">
                    <span className="font-medium">{causeLabel}</span>
                    {cause}
                  </div>
                ) : (
                  <>
                    <div className={sectionLabelClassName}>{causeLabel}</div>
                    {cause ? (
                      <div className="mt-2 text-[12px] leading-5 text-[var(--color-text-2)]">
                        {cause}
                      </div>
                    ) : null}
                  </>
                )}
                {causes.length ? (
                  <ul className={listClassName}>
                    {causes.map((item, index) => (
                      <li key={index} className="flex gap-2">
                        <span className="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-text-3)]" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            {solutionLabel && solutions.length ? (
              <div className={solutionContainerClassName}>
                <div className={solutionLabelClassName}>{solutionLabel}</div>
                <ul className={listClassName}>
                  {solutions.map((item, index) => (
                    <li key={index} className="flex gap-2">
                      <span className={solutionBulletClassName} />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
};

export default TroubleshootingCard;
