interface SelectableRelatedAlertItem {
  id: number;
  similarity_score: number;
  incidents?: unknown[];
}

export const getDefaultSelectedRelatedAlertIds = (
  items: SelectableRelatedAlertItem[]
) => {
  return items
    .filter((item) => item.similarity_score >= 80 && !(item.incidents || []).length)
    .map((item) => item.id);
};

export const getMatchedDimensionsText = (
  matchedDimensions: Record<string, string>
) => {
  const entries = Object.entries(matchedDimensions || {});
  if (!entries.length) {
    return '--';
  }
  return entries.map(([key, value]) => `${key}: ${value}`).join(' / ');
};
