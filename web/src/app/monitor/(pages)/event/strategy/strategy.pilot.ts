import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import { buildTableListContext, tableListMessage } from '@/app/monitor/page-context/tableListContext';

export function getMessage(): PageContextMessage {
  return tableListMessage('monitor-strategy:');
}

export function getTextContext(): Partial<AiPageContext> {
  return buildTableListContext({
    heading: '正在查看告警策略列表',
    identityId: 'strategy-list-identity',
    identityLabel: '当前策略列表',
  });
}

export async function getContext(): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
