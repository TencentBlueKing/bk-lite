'use client';

import { useCallback, useState } from 'react';
import { message, notification, Typography } from 'antd';
import { useCanvasShareApi } from '@/app/ops-analysis/api/dashboardShare';
import type { CanvasShareResourceType } from '@/app/ops-analysis/types/dashboardShare';
import { useTranslation } from '@/utils/i18n';

export type CanvasShareCreatableType = Exclude<CanvasShareResourceType, 'report'>;

/**
 * 统一创建分享入口：createShare → 拼装链接 → 复制 → 提示。
 * Dashboard / Screen / Topology / Architecture 共用，避免各页面各自维护。
 */
export function useCanvasShareAction(resourceType: CanvasShareCreatableType) {
  const { t } = useTranslation();
  const { createShare } = useCanvasShareApi();
  const [shareLoading, setShareLoading] = useState(false);

  const openShare = useCallback(
    async (resourceId?: string | number | null) => {
      if (resourceId == null || resourceId === '' || shareLoading) return;
      setShareLoading(true);
      try {
        const link = await createShare(resourceType, resourceId);
        const shareUrl = `${window.location.origin}${link.url}`;
        try {
          await navigator.clipboard.writeText(shareUrl);
          message.success(t('dashboard.shareLinkCopied'));
        } catch {
          notification.warning({
            message: t('dashboard.shareCopyFailed'),
            description: (
              <Typography.Text copyable={{ text: shareUrl }} className="break-all">
                {shareUrl}
              </Typography.Text>
            ),
            duration: 10,
            placement: 'topRight',
          });
        }
      } catch {
        message.error(t('dashboard.shareCreateFailed'));
      } finally {
        setShareLoading(false);
      }
    },
    [createShare, resourceType, shareLoading, t],
  );

  return { shareLoading, openShare };
}
