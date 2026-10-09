'use client';

import type { MouseEvent } from 'react';

interface SeriesActivationHeaderProps {
  label?: string;
  emphasizedKeys: string[] | null;
  activateLabel: string;
  deactivateLabel: string;
  onActivateAll?: () => void;
  onDeactivateAll?: () => void;
}

const SeriesActivationHeader = ({
  label,
  emphasizedKeys,
  activateLabel,
  deactivateLabel,
  onActivateAll,
  onDeactivateAll
}: SeriesActivationHeaderProps) => {
  const allOn = emphasizedKeys === null;
  const allOff = emphasizedKeys?.length === 0;
  const stop = (event: MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
  };

  return (
    <div className="flex min-w-0 items-center gap-2">
      {label ? <span className="truncate">{label}</span> : null}
      {onActivateAll && onDeactivateAll ? (
        <span className={`${label ? 'ml-auto' : ''} flex flex-shrink-0 items-center gap-2`}>
          <button
            type="button"
            className={`text-xs ${allOn ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-3)]'}`}
            onMouseDown={stop}
            onClick={(event) => {
              stop(event);
              onActivateAll();
            }}
          >
            {activateLabel}
          </button>
          <button
            type="button"
            className={`text-xs ${allOff ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-3)]'}`}
            onMouseDown={stop}
            onClick={(event) => {
              stop(event);
              onDeactivateAll();
            }}
          >
            {deactivateLabel}
          </button>
        </span>
      ) : null}
    </div>
  );
};

export default SeriesActivationHeader;
