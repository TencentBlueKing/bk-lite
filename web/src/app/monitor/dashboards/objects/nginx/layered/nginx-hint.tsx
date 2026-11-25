'use client';

import { ProInfoHint } from '../../host/layered/pro-chrome';
import type { NginxHintCopy } from './hints';

export function NginxHint({ copy }: { copy: NginxHintCopy }) {
  return <ProInfoHint kind={copy.lead} lines={[{ lead: copy.lead, body: copy.body }]} />;
}
