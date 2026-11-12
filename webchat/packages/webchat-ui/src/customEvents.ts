import { isSilentCustomEvent } from '@webchat/core';
import type { CustomProtocolEvent } from './agui';

export function isBlockingHitlEvent(event: CustomProtocolEvent | null): boolean {
  return event?.name === 'approval_request' || event?.name === 'user_choice_request';
}

export function formatDegradedCustomEvent(event: CustomProtocolEvent): string {
  if (isSilentCustomEvent(event.name)) {
    return '';
  }
  const value = event.value;
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const title = typeof record.title === 'string' ? record.title : event.name;
    const description =
      typeof record.description === 'string'
        ? record.description
        : typeof record.content === 'string'
          ? record.content
          : typeof record.markdown === 'string'
            ? record.markdown
            : JSON.stringify(record);
    return `${title}\n${description}`;
  }
  return `${event.name}: ${String(value ?? '')}`;
}
