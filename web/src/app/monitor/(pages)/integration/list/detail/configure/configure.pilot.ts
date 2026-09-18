import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import { pageIdentityFromSearch } from '@/app/monitor/page-context/tableListContext';
import { readVisibleFormFacts } from '@/components/ai-page-context/secretSnapshot';

export function getMessage(): PageContextMessage {
  return {
    title: 'monitor-integration-configure',
    currentTime: pageIdentityFromSearch(['plugin_name', 'name', 'plugin_id']).join('|'),
  };
}

export function getTextContext(): Partial<AiPageContext> {
  const facts = readVisibleFormFacts();
  return {
    url: window.location.href,
    app: 'monitor',
    title: document.title || '接入配置',
    sections: [
      {
        id: 'integration-config',
        label: '接入配置',
        content: [
          '正在查看集成接入配置',
          ...pageIdentityFromSearch(['plugin_name', 'name', 'collect_type', 'template_type']),
          ...facts,
        ].filter(Boolean).join('\n'),
        priority: 9,
      },
    ],
    images: [],
  };
}

export async function getContext(): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
