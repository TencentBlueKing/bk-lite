export const FLOW_RANK_CLASS_KEYS = [
  'flowProtocolRank1',
  'flowProtocolRank2',
  'flowProtocolRank3',
  'flowProtocolRank4',
  'flowProtocolRank5',
] as const;

export const resolveFlowRankClass = (index: number, styleMap: Record<string, string>) => {
  const key = FLOW_RANK_CLASS_KEYS[Math.min(index, FLOW_RANK_CLASS_KEYS.length - 1)];
  return styleMap[key];
};
