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
    'routine_ops': 'workbench.routineOps',
    'monitor_alarm': 'workbench.monitorAlarm',
    'automation': 'workbench.automation',
    'security_audit': 'workbench.securityAudit',
    'performance_analysis': 'workbench.performanceAnalysis',
    'ops_plan': 'workbench.opsPlan',
} satisfies Record<AppTagKey, string>;

export const APP_TAG_COLORS = {
    'routine_ops': { bg: '#E5F4FF', text: '#4A9EFF' },
    'monitor_alarm': { bg: '#FFE5E5', text: '#FF6B9D' },
    'automation': { bg: '#FFF4E5', text: '#FFB84D' },
    'security_audit': { bg: '#E5FFE5', text: '#52C41A' },
    'performance_analysis': { bg: '#F0E5FF', text: '#9B59B6' },
    'ops_plan': { bg: '#E5F0FF', text: '#3498DB' },
} satisfies Record<AppTagKey, AppTagColor>;

const DEFAULT_APP_TAG_COLOR: AppTagColor = {
    bg: '#F0F0F0',
    text: '#666666',
};

const isAppTagKey = (tag: string): tag is AppTagKey => (
    APP_TAGS.includes(tag as AppTagKey)
);

export const getAppTagColor = (tag: string): AppTagColor => (
    isAppTagKey(tag) ? APP_TAG_COLORS[tag] : DEFAULT_APP_TAG_COLOR
);

export const getAppTagLabel = (tag: string, translate: (id: string) => string): string => (
    isAppTagKey(tag) ? translate(APP_TAG_LABEL_KEYS[tag]) : tag
);
