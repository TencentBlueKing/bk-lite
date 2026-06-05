/**
 * 仪表盘无后端预览 story 的共享配置。
 *
 * 取数 API 已在 .storybook/main.ts 中替换为合成数据替身，这里只负责
 * 通过 Next 导航 mock 注入 URL 参数（监控对象 + 实例），让仪表盘以
 * "已选中某实例" 的状态渲染。详见 ../PREVIEW.md。
 */

interface DashboardPreviewParameters {
  readonly layout: 'fullscreen';
  readonly nextjs: {
    readonly appDirectory: true;
    readonly navigation: {
      readonly pathname: string;
      readonly query: Readonly<Record<string, string>>;
    };
  };
}

/**
 * 构建某个仪表盘 story 的 parameters。
 * @param routeKey 仪表盘路由 key（与 registry 中的 key 一致，如 'mysql'、'host'）
 */
export const dashboardPreviewParameters = (routeKey: string): DashboardPreviewParameters => ({
  layout: 'fullscreen',
  nextjs: {
    appDirectory: true,
    navigation: {
      pathname: `/monitor/view/dashboard/${routeKey}`,
      query: {
        monitorObjId: '1',
        instance_id: 'mock-instance-1',
        instance_id_values: 'mock-instance-1',
        instance_id_keys: 'instance_id',
        instance_name: 'mock-host-01'
      }
    }
  }
});
