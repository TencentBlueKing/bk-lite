'use client';

export type { BaseInfoWidgetProps } from '@/app/cmdb/components/public/BaseInfoWidget';

export const widgets = {
  'cmdb.baseInfo': () => import('@/app/cmdb/components/public/BaseInfoWidget'),
} as const;
