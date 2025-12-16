/**
 * 阈值颜色配置
 */

// 默认阈值颜色配置
export const DEFAULT_THRESHOLD_COLORS = [
  { color: '#fd666d', value: '70' }, // 红色 - 危险
  { color: '#EAB839', value: '30' }, // 黄色 - 警告
  { color: '#299C46', value: '0' },  // 绿色 - 正常
];

// 阈值颜色预设方案
export const THRESHOLD_COLOR_PRESETS = {
  default: DEFAULT_THRESHOLD_COLORS,
  traffic: [
    { color: '#ff4d4f', value: '80' },
    { color: '#faad14', value: '50' },
    { color: '#52c41a', value: '0' },
  ],
  temperature: [
    { color: '#ff7a45', value: '60' },
    { color: '#ffa940', value: '40' },
    { color: '#13c2c2', value: '0' },
  ],
};
