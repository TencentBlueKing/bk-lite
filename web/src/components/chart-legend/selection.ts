export type ChartLegendSelection = Record<string, boolean>;

export const isSameChartLegendSelection = (
  left: ChartLegendSelection,
  right: ChartLegendSelection,
): boolean => {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }

  return leftKeys.every((key) => left[key] === right[key]);
};

export const shouldEmitLegendReset = (
  previousKey: string | null,
  nextKey: string,
): boolean => previousKey !== null && previousKey !== nextKey;

export const dispatchChartLegendSelection = (
  chart: { dispatchAction: (payload: Record<string, any>) => void } | null | undefined,
  itemNames: string[],
  selected: ChartLegendSelection,
) => {
  if (!chart || itemNames.length === 0) {
    return;
  }

  const hasSelection = Object.keys(selected).length > 0;

  itemNames.forEach((name) => {
    chart.dispatchAction({
      type: !hasSelection || selected[name] !== false ? 'legendSelect' : 'legendUnSelect',
      name,
    });
  });
};
