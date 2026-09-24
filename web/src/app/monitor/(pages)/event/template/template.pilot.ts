import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import { cleanLabel, selectedTreeLabel, treeSection } from '@/components/ai-page-context/domSnapshot';

const templateLines = (): string[] =>
  Array.from(document.querySelectorAll('button[aria-pressed]')).map((node) => {
    const title = cleanLabel(node.querySelector('[class*="cardTitleText"]')?.textContent || node.textContent || '');
    const selected = node.getAttribute('aria-pressed') === 'true' ? '已勾选' : '未勾选';
    return title ? `${title} (${selected})` : '';
  }).filter(Boolean);

export function getMessage(): PageContextMessage {
  return {
    title: `monitor-policy-template:${selectedTreeLabel() || 'all'}`,
    currentTime: templateLines().slice(0, 12).join('|'),
  };
}

export function getTextContext(): Partial<AiPageContext> {
  const lines = templateLines();
  const groups = Array.from(document.querySelectorAll('[class*="groupName"]'))
    .map((node) => cleanLabel(node.textContent || ''))
    .filter(Boolean);
  return {
    url: window.location.href,
    app: 'monitor',
    title: document.title || '策略模板',
    sections: [
      {
        id: 'template-identity',
        label: '当前策略模板',
        content: [
          '正在查看策略模板',
          selectedTreeLabel() ? `对象: ${selectedTreeLabel()}` : '',
          groups.length ? `分组: ${groups.join('、')}` : '',
          '问答不得替用户勾选或批量应用模板',
        ].filter(Boolean).join('\n'),
        priority: 10,
      },
      ...treeSection(),
      ...(lines.length
        ? [{
          id: 'template-cards',
          label: '当前可见模板',
          content: lines.join('\n'),
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
