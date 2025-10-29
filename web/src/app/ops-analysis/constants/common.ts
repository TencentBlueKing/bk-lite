export interface ChartTypeItem {
  label: string;
  value: string;
}

export const getChartTypeList = (): ChartTypeItem[] => {
  return [
    { label: 'dataSource.lineChart', value: 'line' },
    { label: 'dataSource.barChart', value: 'bar' },
    { label: 'dataSource.pieChart', value: 'pie' },
    { label: 'dataSource.singleValue', value: 'single' },
  ];
};

// 架构图相关常量
export const DEFAULT_COLORS = [
  { id: 'terminal', value: '#C9DBF7' },
  { id: 'teal', value: '#E3FBF7' },
  { id: 'airside', value: '#D9C9F7' },
  { id: 'passenger', value: '#D7FBE3' },
  { id: 'yellow', value: '#FFFBE3' },
  { id: 'pink', value: '#FBE3F7' },
  { id: 'information', value: '#BFF3EE' },
  { id: 'blue', value: '#0066cc' },
  { id: 'green', value: '#00aa00' },
  { id: 'red', value: '#cc0000' },
  { id: 'orange', value: '#ff9900' },
  { id: 'purple', value: '#9900cc' },
  { id: 'black', value: '#000000' },
  { id: 'gray', value: '#666666' },
];
