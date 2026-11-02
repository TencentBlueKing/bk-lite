'use client';

import { ProInfoHint } from '../../host/layered/pro-chrome';

/** 浅色说明。加粗指标名单独一行，下面是释义。 */
export function PostgresHint({
  kind,
  title,
  body
}: {
  kind: string;
  title: string;
  body: string;
}) {
  return (
    <ProInfoHint
      kind={kind}
      label={`${title} ${body}`}
      content={(
        <div className="max-w-[380px] text-[13px] font-normal leading-[1.55] text-[var(--color-text-2)]">
          <strong className="block text-[13px] font-bold leading-[1.55] text-[var(--color-text-1)]">{title}</strong>
          <span className="mt-1 block">{body}</span>
        </div>
      )}
    />
  );
}
