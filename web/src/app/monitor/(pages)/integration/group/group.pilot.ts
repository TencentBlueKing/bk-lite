import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import { buildTableListContext, tableListMessage } from '@/app/monitor/page-context/tableListContext';

export function getMessage(): PageContextMessage {
  return tableListMessage('monitor-org-rule:');
}

export function getTextContext(): Partial<AiPageContext> {
  return buildTableListContext({
    heading: '正在查看组织规则',
    identityId: 'group-list-identity',
    identityLabel: '当前组织规则',
  });
}

export async function getContext(): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
