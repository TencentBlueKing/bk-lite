import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import { buildTableListContext, tableListMessage } from '@/app/monitor/page-context/tableListContext';

export function getMessage(): PageContextMessage {
  return tableListMessage('monitor-object:');
}

export function getTextContext(): Partial<AiPageContext> {
  return buildTableListContext({
    heading: '正在查看监控对象',
    identityId: 'object-list-identity',
    identityLabel: '当前对象',
  });
}

export async function getContext(): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
