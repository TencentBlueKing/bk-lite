/**
 * 专业仪表盘注册表对外入口。
 * 元数据与组件加载分离：权限/URL/侧栏只依赖 metadata，组件按需 dynamic import。
 */
export {
  PROFESSIONAL_DASHBOARD_GROUPS,
  PROFESSIONAL_DASHBOARD_METADATA,
  PROFESSIONAL_DASHBOARDS,
  findProfessionalDashboardMeta,
  findProfessionalDashboardMetaByKey,
  getDashboardObjectMatchKeys,
  getProfessionalDashboardKey,
  getProfessionalObjectDisplayName,
  getProfessionalDashboardUrl,
  getProfessionalDashboardPermissionPath
} from './metadata';

export { loadDashboardComponent, DASHBOARD_COMPONENT_LOADERS } from './component-loaders';
