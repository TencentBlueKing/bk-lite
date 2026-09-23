import { HandledRequestError } from '@/utils/request';

type Translate = (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string;

/** Map RUM BFF / request errors to product copy. */
export function rumErrorMessage(err: unknown, t: Translate): string {
  if (err instanceof HandledRequestError) {
    switch (err.code) {
      case 'rum_unavailable':
      case 'unavailable':
        return t('rum.common.unavailable', 'RUM 控制面暂不可用，请检查 RUM controller 连接');
      case 'rum_analytics_unavailable':
        return t('rum.analytics.unavailable', '体验分析暂不可用。仍可管理应用与接入配置。');
      case 'revision_conflict':
      case 'conflict':
        return t('rum.common.conflict', '应用状态已被他人更新，请刷新后重试');
      case 'not_found':
        return t('rum.common.notFound', '应用不存在');
      case 'forbidden':
        return t('rum.common.forbidden', '没有权限执行此操作');
      default:
        return err.message || t('rum.common.genericError', '操作失败，请稍后重试');
    }
  }
  if (err instanceof Error && err.message) return err.message;
  return t('rum.common.genericError', '操作失败，请稍后重试');
}
