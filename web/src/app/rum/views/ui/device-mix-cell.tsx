'use client';

import { DesktopOutlined, MobileOutlined } from '@ant-design/icons';
import { Tooltip } from 'antd';

import type { RumViewDeviceMix } from '@/app/rum/api';
import { useTranslation } from '@/utils/i18n';

export default function DeviceMixCell({ mix }: { mix: RumViewDeviceMix }) {
  const { t } = useTranslation();
  const total = mix.mobile + mix.desktop;
  if (total <= 0) return <span className="text-[var(--color-text-3)]">—</span>;
  const mobilePct = Math.round((mix.mobile / total) * 100);
  const desktopPct = 100 - mobilePct;
  return (
    <div className="flex items-center gap-2">
      <Tooltip title={t('rum.views.device.mobile', '移动')}>
        <span className="inline-flex items-center gap-1 tabular-nums">
          <MobileOutlined aria-hidden="true" className="text-[var(--color-text-3)]" />
          {mobilePct}%
        </span>
      </Tooltip>
      <Tooltip title={t('rum.views.device.desktop', '桌面')}>
        <span className="inline-flex items-center gap-1 tabular-nums">
          <DesktopOutlined aria-hidden="true" className="text-[var(--color-text-3)]" />
          {desktopPct}%
        </span>
      </Tooltip>
    </div>
  );
}
