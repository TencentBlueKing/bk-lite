export interface AlarmBreadcrumbMenuItem {
  title: string;
  url: string;
  children?: AlarmBreadcrumbMenuItem[];
}

export interface AlarmBreadcrumbMenus {
  zh: AlarmBreadcrumbMenuItem[];
  en: AlarmBreadcrumbMenuItem[];
}

export const defaultAlarmBreadcrumbMenus: AlarmBreadcrumbMenus = {
  zh: [
    {
      title: '事故',
      url: '/alarm/incidents',
      children: [
        {
          title: '事故详情',
          url: '/alarm/incidents/detail',
        },
      ],
    },
    {
      title: '告警',
      url: '/alarm/alarms',
    },
    {
      title: '集成',
      url: '/alarm/integration',
      children: [
        {
          title: '告警源详情',
          url: '/alarm/integration/detail',
        },
      ],
    },
    {
      title: '配置',
      url: '/alarm/settings',
      children: [
        {
          title: '相关性规则',
          url: '/alarm/settings/correlationRules',
        },
        {
          title: '告警分派',
          url: '/alarm/settings/alertAssign',
        },
        {
          title: '屏蔽策略',
          url: '/alarm/settings/shieldStrategy',
        },
        {
          title: '告警丰富',
          url: '/alarm/settings/alertEnrichment',
        },
        {
          title: '全局配置',
          url: '/alarm/settings/globalConfig',
        },
        {
          title: '操作日志',
          url: '/alarm/settings/operationLog',
        },
      ],
    },
  ],
  en: [
    {
      title: 'Incident',
      url: '/alarm/incidents',
      children: [
        {
          title: 'Incident Detail',
          url: '/alarm/incidents/detail',
        },
      ],
    },
    {
      title: 'Alarms',
      url: '/alarm/alarms',
    },
    {
      title: 'Integration',
      url: '/alarm/integration',
      children: [
        {
          title: 'Source Detail',
          url: '/alarm/integration/detail',
        },
      ],
    },
    {
      title: 'Settings',
      url: '/alarm/settings',
      children: [
        {
          title: 'Correlation Rules',
          url: '/alarm/settings/correlationRules',
        },
        {
          title: 'Alert Assignment',
          url: '/alarm/settings/alertAssign',
        },
        {
          title: 'Shield Strategy',
          url: '/alarm/settings/shieldStrategy',
        },
        {
          title: 'Alert Enrichment',
          url: '/alarm/settings/alertEnrichment',
        },
        {
          title: 'Global Configuration',
          url: '/alarm/settings/globalConfig',
        },
        {
          title: 'Operation Log',
          url: '/alarm/settings/operationLog',
        },
      ],
    },
  ],
};
