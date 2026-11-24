import { expect, it } from 'vitest';
import menu from './menu.json';

it.each(['zh', 'en'] as const)('%s 应用菜单仅显示保留的业务入口', locale => {
  const applications = menu[locale].find(item => item.url === '/itsm/apps');
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
  const settings = menu[locale].find(item => item.url === '/itsm/settings');
  const templateMenus = settings?.children?.filter(item => ['survey', 'print'].includes(item.name));

  expect(templateMenus).toEqual([
    { title: surveyTitle, url: '/itsm/settings/survey-templates', name: 'survey' },
    { title: printTitle, url: '/itsm/settings/print-templates', name: 'print' },
  ]);
});
