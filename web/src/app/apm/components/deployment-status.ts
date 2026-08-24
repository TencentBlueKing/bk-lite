import type { ApmDeploymentStatus } from '@/app/apm/types';

export const DEPLOYMENT_STATUS_META: Record<
  ApmDeploymentStatus,
  { labelKey: string; fallback: string; tone: 'success' | 'info' | 'warning' | 'danger' }
> = {
  success: { labelKey: 'apm.home.releaseSuccess', fallback: '成功', tone: 'success' },
  in_progress: { labelKey: 'apm.home.releaseInProgress', fallback: '进行中', tone: 'info' },
  rollback: { labelKey: 'apm.home.releaseRollback', fallback: '回滚', tone: 'warning' },
  failed: { labelKey: 'apm.home.releaseFailed', fallback: '失败', tone: 'danger' },
};

export const DEPLOYMENT_LOOKBACK_MS = 90 * 24 * 60 * 60 * 1000;
