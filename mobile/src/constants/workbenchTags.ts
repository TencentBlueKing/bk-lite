export const APP_TAGS = [
  'routine_ops',
  'monitor_alarm',
  'automation',
  'security_audit',
  'performance_analysis',
  'ops_plan',
] as const;

export type AppTagKey = typeof APP_TAGS[number];

export interface AppTagColor {
  bg: string;
  text: string;
}

export const APP_TAG_LABEL_KEYS = {
  routine_ops: 'workbench.routineOps',
  monitor_alarm: 'workbench.monitorAlarm',
  automation: 'workbench.automation',
  security_audit: 'workbench.securityAudit',
  performance_analysis: 'workbench.performanceAnalysis',
  ops_plan: 'workbench.opsPlan',
} satisfies Record<AppTagKey, string>;

export const APP_TAG_COLORS = {
  routine_ops: { bg: '#EDF4FF', text: '#155AEF' },
  monitor_alarm: { bg: '#F4F5F8', text: '#F43B2C' },
  automation: { bg: '#F4F5F8', text: '#FF9C07' },
  security_audit: { bg: '#F4F5F8', text: '#27C274' },
  performance_analysis: { bg: '#F4F5F8', text: '#475468' },
  ops_plan: { bg: '#e1edfc', text: '#155AEF' },
} satisfies Record<AppTagKey, AppTagColor>;

const DEFAULT_APP_TAG_COLOR: AppTagColor = {
  bg: '#F4F5F8',
  text: '#475468',
};

const APP_TAG_CLASS_KEYS = {
  routine_ops: 'tagRoutine',
  monitor_alarm: 'tagMonitor',
  automation: 'tagAutomation',
  security_audit: 'tagSecurity',
  performance_analysis: 'tagPerformance',
  ops_plan: 'tagOps',
} satisfies Record<AppTagKey, string>;

const isAppTagKey = (tag: string): tag is AppTagKey => (
  APP_TAGS.includes(tag as AppTagKey)
);

export const getAppTagColor = (tag: string): AppTagColor => (
  isAppTagKey(tag) ? APP_TAG_COLORS[tag] : DEFAULT_APP_TAG_COLOR
);

export const getAppTagClassKey = (tag: string): string => (
  isAppTagKey(tag) ? APP_TAG_CLASS_KEYS[tag] : 'tag'
);

export const getAppTagLabel = (tag: string, translate: (id: string) => string): string => (
  isAppTagKey(tag) ? translate(APP_TAG_LABEL_KEYS[tag]) : tag
);
