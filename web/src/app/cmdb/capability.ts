'use client';

export type { BaseInfoWidgetProps } from '@/app/cmdb/components/public/BaseInfoWidget';
export type { AssetChangeWidgetProps } from '@/app/cmdb/components/public/AssetChangeWidget';

export const widgets = {
  'cmdb.baseInfo': () => import('@/app/cmdb/components/public/BaseInfoWidget'),
  'cmdb.assetChange': () =>
    import('@/app/cmdb/components/public/AssetChangeWidget'),
} as const;
