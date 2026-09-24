import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import { buildTableListContext, tableListMessage } from '@/app/monitor/page-context/tableListContext';

export function getMessage(): PageContextMessage {
  return tableListMessage('monitor-asset:');
}

export function getTextContext(): Partial<AiPageContext> {
  return buildTableListContext({
    heading: '正在查看监控资产',
    identityId: 'asset-list-identity',
    identityLabel: '当前资产',
  });
}

export async function getContext(): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
