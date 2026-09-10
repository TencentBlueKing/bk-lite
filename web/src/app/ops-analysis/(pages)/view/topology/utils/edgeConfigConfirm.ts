export interface EdgeConfigConfirmValues {
  lineType: 'common_line' | 'network_line';
  lineName?: string;
  styleConfig?: {
    lineColor?: string;
    lineWidth?: number;
    lineStyle?: 'line' | 'dotted' | 'point';
    enableAnimation?: boolean;
  };
  sourceInterface?: {
    type: 'existing' | 'custom';
    value: string;
  };
  targetInterface?: {
    type: 'existing' | 'custom';
    value: string;
  };
}

export function applyEdgeConfigConfirm<T extends object>(
  previousData: T | null | undefined,
  values: EdgeConfigConfirmValues,
  vertices?: Array<{ x: number; y: number }>,
): T & {
  lineType: EdgeConfigConfirmValues['lineType'];
  lineName?: string;
  styleConfig?: EdgeConfigConfirmValues['styleConfig'];
  vertices?: Array<{ x: number; y: number }>;
  sourceInterface?: EdgeConfigConfirmValues['sourceInterface'];
  targetInterface?: EdgeConfigConfirmValues['targetInterface'];
} {
  return {
    ...(previousData ?? ({} as T)),
    lineType: values.lineType,
    lineName: values.lineName,
    styleConfig: values.styleConfig,
    vertices,
    sourceInterface: values.sourceInterface,
    targetInterface: values.targetInterface,
  };
}
