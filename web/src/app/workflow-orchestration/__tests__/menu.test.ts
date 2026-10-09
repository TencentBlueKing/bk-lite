import menu from '@/app/workflow-orchestration/constants/menu.json';

describe('编排中心路由菜单契约', () => {
  it.each(['zh', 'en'] as const)('%s 菜单独立暴露首页、流程与执行记录', (locale) => {
    expect(menu[locale].filter((item) => !item.isNotMenuItem).map((item) => ({ name: item.name, url: item.url }))).toEqual([
      { name: 'workflow', url: '/workflow-orchestration/home' },
      { name: 'workflow', url: '/workflow-orchestration/workflows' },
      { name: 'workflow', url: '/workflow-orchestration/executions' },
    ]);
  });

  it.each(['zh', 'en'] as const)('%s 根入口保留隐藏权限路由', (locale) => {
    expect(menu[locale].find((item) => item.url === '/workflow-orchestration')?.isNotMenuItem).toBe(true);
  });
});
