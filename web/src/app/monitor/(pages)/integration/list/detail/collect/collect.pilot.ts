import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import { pageIdentityFromSearch } from '@/app/monitor/page-context/tableListContext';

export function getMessage(): PageContextMessage {
  return {
    title: 'monitor-collect-template',
    currentTime: pageIdentityFromSearch(['plugin_id', 'template_type']).join('|'),
  };
}

export function getTextContext(): Partial<AiPageContext> {
  return {
    url: window.location.href,
    app: 'monitor',
    title: document.title || '采集模板',
    sections: [{
      id: 'collect-template',
      label: '采集模板',
      content: [
        '正在查看采集模板',
        ...pageIdentityFromSearch(['plugin_id', 'plugin_name', 'template_type', 'name']),
        '模板正文含密钥，未采集',
      ].join('\n'),
      priority: 8,
    }],
    images: [],
  };
}

export async function getContext(): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
