'use client';

import { ProInfoHint } from '../../host/layered/pro-chrome';
import type { NginxHintCopy } from './hints';

export function NginxHint({ copy }: { copy: NginxHintCopy | readonly NginxHintCopy[] }) {
  const lines = Array.isArray(copy) ? copy : [copy];
  return (
    <ProInfoHint
      kind={lines[0]?.lead || '说明'}
      label={lines.map((line) => line.lead).join(' ')}
      content={(
        <div className="max-w-[360px]">
          {lines.map((line) => (
            <div key={line.lead} className="mb-2 last:mb-0">
              <div className="text-[13px] font-semibold text-[var(--color-text-1)]">{line.lead}</div>
              <div className="mt-1 whitespace-pre-line text-[13px] font-normal leading-[1.55] text-[var(--color-text-3)]">{line.body}</div>
            </div>
          ))}
        </div>
      )}
    />
  );
}
