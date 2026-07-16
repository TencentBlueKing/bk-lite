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
