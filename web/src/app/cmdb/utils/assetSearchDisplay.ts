export type ChangeOperationTone =
  | 'create'
  | 'update'
  | 'delete'
  | 'execute'
  | 'relation'
  | 'unknown';

export interface StableTypeStyle {
  color: string;
  borderColor: string;
  background: string;
}

const TYPE_STYLE_PALETTE: StableTypeStyle[] = [
  { color: '#1f63e9', borderColor: '#bfd5ff', background: '#f4f8ff' },
  { color: '#0f8bc9', borderColor: '#bfe6ff', background: '#f1f9ff' },
  { color: '#0a8f7a', borderColor: '#b9eee5', background: '#effbf9' },
  { color: '#1c9b58', borderColor: '#b8ebd0', background: '#effbf5' },
  { color: '#7a4be8', borderColor: '#dccfff', background: '#f7f3ff' },
  { color: '#a23bd6', borderColor: '#edc9ff', background: '#fbf2ff' },
  { color: '#d6367c', borderColor: '#ffc7df', background: '#fff2f8' },
  { color: '#e5485a', borderColor: '#ffc9d1', background: '#fff3f5' },
  { color: '#d96b15', borderColor: '#ffd8b2', background: '#fff7ed' },
  { color: '#b88900', borderColor: '#ffe3a3', background: '#fff9e8' },
  { color: '#5268e8', borderColor: '#cdd5ff', background: '#f5f6ff' },
  { color: '#2870c7', borderColor: '#c4ddff', background: '#f3f8ff' },
  { color: '#008eaa', borderColor: '#b9eaf2', background: '#effbfe' },
  { color: '#6f7c13', borderColor: '#e1eaa8', background: '#fafbea' },
  { color: '#c747a4', borderColor: '#ffccec', background: '#fff3fb' },
  { color: '#995fdb', borderColor: '#e0ceff', background: '#f8f4ff' },
];

export const getChangeOperationTone = (
  type?: string
): { labelKey: string; tone: ChangeOperationTone } => {
  switch (type) {
    case 'create_entity':
      return { labelKey: 'AssetSearch.operationTypes.create', tone: 'create' };
    case 'update_entity':
      return { labelKey: 'AssetSearch.operationTypes.update', tone: 'update' };
    case 'delete_entity':
      return { labelKey: 'AssetSearch.operationTypes.delete', tone: 'delete' };
    case 'execute':
      return { labelKey: 'AssetSearch.operationTypes.execute', tone: 'execute' };
    case 'create_edge':
      return { labelKey: 'AssetSearch.operationTypes.createRelation', tone: 'relation' };
    case 'delete_edge':
      return { labelKey: 'AssetSearch.operationTypes.deleteRelation', tone: 'relation' };
    default:
      return { labelKey: 'AssetSearch.operationTypes.unknown', tone: 'unknown' };
  }
};

const getStableTypeHash = (value: string) => {
  let hash = 0;
  Array.from(value).forEach((char) => {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  });
  return hash;
};

export const getStableTypeStyle = (value?: string): StableTypeStyle => {
  if (!value) {
    return TYPE_STYLE_PALETTE[1];
  }
  return TYPE_STYLE_PALETTE[getStableTypeHash(value) % TYPE_STYLE_PALETTE.length];
};
