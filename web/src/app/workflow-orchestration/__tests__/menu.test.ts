import menu from '@/app/workflow-orchestration/constants/menu.json';

describe('编排中心路由菜单契约', () => {
  it.each(['zh', 'en'] as const)('%s 菜单按首页、流程、模版和执行记录分开授权', (locale) => {
    const visible = menu[locale].filter((item) => !item.isNotMenuItem);
    expect(visible.map((item) => ({ name: item.name, url: item.url }))).toEqual([
      { name: 'workflow_home', url: '/workflow-orchestration/home' },
      { name: 'workflow', url: '/workflow-orchestration/workflows' },
      { name: 'workflow_execution', url: '/workflow-orchestration/executions' },
    ]);
    expect(visible.find((item) => item.url === '/workflow-orchestration/workflows')?.children?.map((item) => ({
      title: item.title,
      name: item.name,
      url: item.url,
      withParentPermission: item.withParentPermission,
    }))).toEqual(locale === 'zh' ? [
      { title: '流程', name: 'workflow', url: '/workflow-orchestration/workflows', withParentPermission: undefined },
      { title: '模版', name: 'workflow_market', url: '/workflow-orchestration/market', withParentPermission: undefined },
    ] : [
      { title: 'Workflows', name: 'workflow', url: '/workflow-orchestration/workflows', withParentPermission: undefined },
      { title: 'Templates', name: 'workflow_market', url: '/workflow-orchestration/market', withParentPermission: undefined },
    ]);
  });

  it.each(['zh', 'en'] as const)('%s 根入口保留隐藏权限路由', (locale) => {
    expect(menu[locale].find((item) => item.url === '/workflow-orchestration')?.isNotMenuItem).toBe(true);
  });
});
