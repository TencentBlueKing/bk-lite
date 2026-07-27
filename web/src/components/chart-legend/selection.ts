export type ChartLegendSelection = Record<string, boolean>;

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
