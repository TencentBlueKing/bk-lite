/**
 * 报警中心模块 - 语义色集中映射
 *
 * 设计准则（参见 cmdb/DESIGN.md §1）：
 *  - 业务语义色（状态、健康度、品牌色）一律走本文件，禁止散落到组件内。
 *  - 暗色模式如何映射：当前仅定义 light，暗色时若需独立色值，在本文件内补 `*_DARK`
 *    并在使用点用主题判断切换。目前业务多数色用于状态徽章/趋势图，
 *    在暗色背景下未发现明显对比度问题，暂不补充。
 *  - 严格保留与原代码相同的 hex 值，避免视觉变更。
 *
 * 值与全局 token 的关系：
 *  - PRIMARY 与 `--color-primary` (#155AEF) 不同（业务自有 #2F6BFF）
 *  - FAIL_BRAND 与 `--color-fail` (#F43B2C) 一致
 *  - SUCCESS_GREEN 与 `--color-success` (#27C274) 不同（业务自有 #00ba6c）
 *  这是历史原因，重构色板前保持原值。
 */

/** 品牌色 */
export const BRAND = {
  /** 品牌蓝（用于强调、选中态背景指示） */
  PRIMARY: '#2F6BFF',
  /** 品牌红（用于等级标识等） */
  FAIL: '#F43B2C',
  /** 默认等级琥珀色（无 color 字段时的 fallback） */
  LEVEL_FALLBACK_AMBER: '#FFAD42',
} as const;

/** 文本/背景中性色 */
export const NEUTRAL = {
  /** 白色文本（深色徽章/Tag 内） */
  ON_DARK_FG: '#fff',
} as const;

/** 状态文字色（成功/失败/警告/中性） */
export const STATUS_TEXT = {
  /** 生效/激活/上行（红色趋势文字） */
  ACTIVE_GREEN: '#00ba6c',
  /** 失效/失败 */
  INACTIVE_RED: '#CE241B',
  /** 趋势↑ 红色 */
  TREND_UP_RED: '#f53f3f',
  /** 趋势↓ 绿色 */
  TREND_DOWN_GREEN: '#00b42a',
  /** 警告橙 */
  WARN_ORANGE: '#ff7d00',
  /** 中性灰 */
  NEUTRAL_GRAY: '#86909c',
} as const;

/** 健康状态背景色（淡色） */
export const HEALTH_BG = {
  RED_BG: '#fff1f0',
  ORANGE_BG: '#fff7e8',
  GREEN_BG: '#e8ffea',
  GRAY_BG: '#f2f3f5',
  BLUE_BG: '#e8f0ff',
} as const;

/** 集成源 logo 主色（按 source_id 选） */
export const SOURCE_LOGO: Record<string, string> = {
  restful: '#5b8def',
  nats: '#27aae1',
  k8s: '#326ce5',
  snmp_trap: '#2b3040',
  prometheus: '#e6522c',
  zabbix: '#2b3040',
};

/** 集成源 logo fallback */
export const SOURCE_LOGO_FALLBACK = '#3370ff';
