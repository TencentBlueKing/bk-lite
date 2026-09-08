export interface KnowledgeBase {
  id: number;
  name: string;
  introduction?: string;
}

export interface SelectorOption {
  id: number;
  name: string;
  icon?: string;
  description?: string;
}

export interface KnowledgeBaseRagSource {
  id: number;
  name: string;
  introduction: string;
  score?: number;
}

export const defaultIconTypes = [
  'zhishiku',
  'zhishiku-red',
  'zhishiku-blue',
  'zhishiku-yellow',
  'zhishiku-green',
];

export const getIconTypeByIndex = (
  index: number,
  iconTypes: string[] = defaultIconTypes,
): string => iconTypes[index % iconTypes.length] || 'zhishiku';

export const resolveOptionIcon = (
  name?: string,
  icon?: string,
): string => {
  const n = (name || '').toLowerCase();
  if (n.includes('mysql')) return 'mysql';
  if (n.includes('redis')) return 'redis';
  if (n.includes('oracle')) return 'oracle';
  if (n.includes('postgres')) return 'postgresql';
  if (n.includes('elastic')) return 'elasticsearch';
  if (n.includes('shell') || n.includes('ssh') || n.includes('linux')) return 'linux';
  if (n.includes('http') || n.includes('api') || n.includes('请求')) return 'api';
  if (n.includes('知识库') || n.includes('knowledge')) return 'zhishiku';
  if (icon && icon !== 'gongjuji' && icon !== 'zhishiku') return icon;
  return 'gongju';
};
