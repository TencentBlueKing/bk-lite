/** 未选或清空时左图全显。有选中时只留选中项。右栏候选项不在这里裁。 */
export const filterPlotted = <T extends { id: string }>(
  items: readonly T[],
  selected: ReadonlySet<string>
): T[] => {
  if (selected.size === 0) return [...items];
  const picked = items.filter((item) => selected.has(item.id));
  return picked.length ? picked : [...items];
};
