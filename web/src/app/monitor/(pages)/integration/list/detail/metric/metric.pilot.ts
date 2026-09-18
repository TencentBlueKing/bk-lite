import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import { cleanLabel } from '@/components/ai-page-context/domSnapshot';
import { buildTableListContext, pageIdentityFromSearch } from '@/app/monitor/page-context/tableListContext';

const groupTitles = (): string[] =>
  Array.from(document.querySelectorAll('.collapse-title .title, .title'))
    .map((node) => cleanLabel(node.textContent || ''))
    .filter(Boolean)
    .slice(0, 40);

export function getMessage(): PageContextMessage {
  return {
    title: 'monitor-plugin-metrics',
    currentTime: groupTitles().slice(0, 8).join('|'),
  };
}

export function getTextContext(): Partial<AiPageContext> {
  const groups = groupTitles();
  const table = buildTableListContext({
    heading: '正在查看插件指标目录',
    extraIdentity: pageIdentityFromSearch(['plugin_name', 'name']),
    identityId: 'plugin-metric-identity',
    identityLabel: '插件指标目录',
  });
  return {
    ...table,
    sections: [
      ...(table.sections || []),
      ...(groups.length
        ? [{
          id: 'plugin-metric-groups',
          label: '当前分组',
          content: groups.join('\n'),
          priority: 5,
        }]
        : []),
    ],
  };
}

export async function getContext(): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
