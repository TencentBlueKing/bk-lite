import type { RoomLayoutData } from '@/app/cmdb/types/rackRoom';

// 科技写实主题色板（深色背景 + 霓虹描边）
export const TECH = {
  bg0: '#0a0f1c',
  bg1: '#0e1424',
  panel: '#111a2e',
  panelHi: '#16223c',
  line: 'rgba(86,160,255,0.16)',
  lineHi: 'rgba(120,190,255,0.5)',
  cyan: '#3fd0ff',
  text: '#dbe6ff',
  textDim: '#7e92bd',
  ok: '#36e6a0',
  warn: '#ffb547',
  danger: '#ff5a6a',
};

// 机柜类型枚举 → 主色（普通/网络/存储/配电/配线/其他）
export const RACK_TYPE_COLOR: Record<string, string> = {
  '1': '#3f8cff', // 普通柜
  '2': '#22c98a', // 网络柜
  '3': '#f2a93b', // 存储柜
  '4': '#ff5a6a', // 配电柜
  '5': '#d65bd0', // 配线柜
  other: '#9b7bff', // 其他柜
};

export const RACK_TYPE_NAME: Record<string, string> = {
  '1': '普通柜', '2': '网络柜', '3': '存储柜',
  '4': '配电柜', '5': '配线柜', other: '其他柜',
};

export const rackTypeColor = (t: string | null): string =>
  (t && RACK_TYPE_COLOR[t]) || RACK_TYPE_COLOR.other;

export const rackTypeName = (t: string | null): string =>
  (t && RACK_TYPE_NAME[t]) || RACK_TYPE_NAME.other;

// 网格渲染尺寸：至少 12 列 × 12 行（对齐参考截图），不足补足
export const roomGridSize = (data: RoomLayoutData) => ({
  cols: Math.max(12, data.grid.max_col),
  rows: Math.max(12, data.grid.max_row),
});

export const CELL = 116;  // 网格单元像素
export const PAD = 42;    // 行/列标题留白
export const GAP = 14;    // 机柜与格线间距

export const cellXY = (row: number, col: number) => ({
  x: PAD + (col - 1) * CELL,
  y: PAD + (row - 1) * CELL,
});

// U → 正视图 y/height（U1 在底部）
export const U_PX = 15;          // 每 U 像素
export const RACK_TOP = 10;      // 机柜框上内边距
export const uRect = (uCount: number, uStart: number, uSize: number) => ({
  y: RACK_TOP + (uCount - (uStart + uSize - 1)) * U_PX,
  height: uSize * U_PX,
});

export const rackInnerHeight = (uCount: number) => uCount * U_PX + RACK_TOP * 2;

// 设备模型 → 侧条色 + 名称（仅类型语义，不接告警）
export const DEVICE_TYPE_COLOR: Record<string, string> = {
  switch: '#22c98a',
  router: '#2ec1c8',
  firewall: '#ff5a6a',
  loadbalance: '#f2a93b',
  physcial_server: '#3f8cff',
};
export const DEVICE_TYPE_NAME: Record<string, string> = {
  switch: '交换机', router: '路由器', firewall: '防火墙',
  loadbalance: '负载均衡', physcial_server: '物理服务器',
};
export const deviceColor = (m: string): string => DEVICE_TYPE_COLOR[m] || '#6b7280';
export const deviceTypeName = (m: string): string => DEVICE_TYPE_NAME[m] || m;
