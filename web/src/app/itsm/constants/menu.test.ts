import { expect, it } from 'vitest';
import menu from './menu.json';

it.each(['zh', 'en'] as const)('%s 应用菜单仅显示保留的业务入口', locale => {
  const applications = menu[locale].find(item => item.name === 'knowledge');
  expect(applications?.children?.map(item => item.url)).toEqual([
    '/itsm/apps/knowledge',
    '/itsm/apps/duty',
    '/itsm/apps/change',
    '/itsm/apps/handover',
  ]);
});

it.each([
  ['zh', '满意度模板', '打印预览'],
  ['en', 'Satisfaction templates', 'Print preview'],
] as const)('%s 设置菜单提供满意度模板和打印预览', (locale, surveyTitle, printTitle) => {
  const settings = menu[locale].find(item => item.name === 'setting');
  const templateMenus = settings?.children?.filter(item => ['survey', 'print'].includes(item.name));

  expect(templateMenus).toEqual([
    { title: surveyTitle, url: '/itsm/settings/survey-templates', name: 'survey' },
    { title: printTitle, url: '/itsm/settings/print-templates', name: 'print' },
  ]);
});

it.each([
  ['zh', ['服务门户', '工单中心', '业务协作', '流程设计', '表单与集成', '自动化与时效', '管理设置']],
  ['en', ['Service portal', 'Ticket center', 'Team operations', 'Workflow design', 'Forms and integrations', 'Automation and SLA', 'Administration']],
] as const)('%s 先展示日常工作，再展示设计和管理工具', (locale, titles) => {
  expect(menu[locale].map(tab => tab.title)).toEqual(titles);
  expect(menu[locale].map(tab => tab.name)).toEqual(['portal', 'ticket', 'knowledge', 'workflow', 'form', 'rule', 'setting']);
});

it.each(['zh', 'en'] as const)('%s 跨权限分组使用目录，首个可访问入口为可见业务页', locale => {
  const cases = [
    ['knowledge', 'duty', '/itsm/apps/duty'],
    ['form', 'data', '/itsm/form/dictionaries'],
    ['rule', 'status_stage', '/itsm/rule/status'],
    ['setting', 'print', '/itsm/settings/print-templates'],
  ];
  for (const [groupName, permission, destination] of cases) {
    const group = menu[locale].find(item => item.name === groupName);
    expect(group).toBeDefined();
    expect(group).not.toHaveProperty('url');
    const firstAccessible = group?.children.find(child =>
      child.name === permission || ('isNotMenuItem' in child && child.isNotMenuItem)
    );
    expect(firstAccessible?.url).toBe(destination);
  }
});

it.each(['zh', 'en'] as const)('%s 业务协作使用随导航状态变色的组织图标', locale => {
  expect(menu[locale].find(item => item.name === 'knowledge')?.icon).toBe('zuzhiguanli');
});
