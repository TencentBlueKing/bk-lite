import type { AiContextSection, AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import {
  cleanLabel,
  readPaginationRange,
  readTableRows,
  readTreeLines,
  selectedTreeLabel,
  treeSection,
} from '@/components/ai-page-context/domSnapshot';

export const fingerprintRows = (rows: string[]): string =>
  rows.slice(0, 12).map((row) => row.slice(0, 48)).join('|');

export const buildTableListContext = (options: {
  heading: string;
  extraIdentity?: string[];
  identityId?: string;
  identityLabel?: string;
  root?: Element | Document | null;
}): Partial<AiPageContext> => {
  const root = options.root || document;
  const rows = readTableRows(root);
  const range = readPaginationRange(root);
  const objectLabel = selectedTreeLabel();
  const identity = [
    options.heading,
    objectLabel ? `对象: ${objectLabel}` : '',
    ...(options.extraIdentity || []),
  ].filter(Boolean);
  const sections: AiContextSection[] = [
    {
      id: options.identityId || 'list-identity',
      label: options.identityLabel || '当前列表',
      content: identity.join('\n'),
      priority: 10,
    },
    ...treeSection(root),
    ...(range
      ? [{
        id: 'list-range',
        label: '结果范围',
        content: range,
        priority: 8,
      }]
      : []),
    ...(rows.length
      ? [{
        id: 'list-table',
        label: '当前页',
        content: rows.join('\n'),
        priority: 4,
      }]
      : []),
  ];
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'monitor',
    title: typeof document === 'undefined' ? '' : document.title,
    sections,
    images: [],
  };
};

export const tableListMessage = (titlePrefix: string): PageContextMessage => {
  const rows = readTableRows();
  const range = readPaginationRange();
  const objectLabel = selectedTreeLabel();
  const tree = readTreeLines();
  const title = `${titlePrefix}${objectLabel || 'all'}`;
  const currentTime = [objectLabel, range, fingerprintRows(rows), fingerprintRows(tree)]
    .filter(Boolean)
    .join('::');
  return currentTime ? { title, currentTime } : { title };
};

export const pageIdentityFromSearch = (keys: string[]): string[] => {
  if (typeof window === 'undefined') return [];
  const params = new URLSearchParams(window.location.search);
  return keys
    .map((key) => {
      const value = params.get(key);
      return value ? `${key}: ${cleanLabel(value)}` : '';
    })
    .filter(Boolean);
};
