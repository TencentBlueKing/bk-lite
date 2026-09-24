import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import { cleanLabel, selectedTreeLabel, treeSection } from '@/components/ai-page-context/domSnapshot';
import { pageIdentityFromSearch } from '@/app/monitor/page-context/tableListContext';

const cardLines = (): string[] =>
  Array.from(document.querySelectorAll('h2')).map((node) => {
    const title = cleanLabel(node.textContent || '');
    const tag = cleanLabel(node.parentElement?.querySelector('.ant-tag')?.textContent || '');
    return [title, tag].filter(Boolean).join(' · ');
  }).filter(Boolean);

export function getMessage(): PageContextMessage {
  return {
    title: `monitor-integration-list:${selectedTreeLabel() || 'all'}`,
    currentTime: cardLines().slice(0, 8).join('|'),
  };
}

export function getTextContext(): Partial<AiPageContext> {
  const cards = cardLines();
  return {
    url: window.location.href,
    app: 'monitor',
    title: document.title || '集成列表',
    sections: [
      {
        id: 'integration-list-identity',
        label: '当前集成列表',
        content: [
          '正在查看集成列表',
          selectedTreeLabel() ? `对象: ${selectedTreeLabel()}` : '',
          ...pageIdentityFromSearch(['name']),
        ].filter(Boolean).join('\n'),
        priority: 10,
      },
      ...treeSection(),
      ...(cards.length
        ? [{
          id: 'integration-list-cards',
          label: '当前可见插件',
          content: cards.join('\n'),
          priority: 4,
        }]
        : []),
    ],
    images: [],
  };
}

export async function getContext(): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
