'use client';

export type { AlertRawLogWidgetProps } from '@/app/log/components/public/AlertRawLogWidget';

export const widgets = {
  'log.alertRawLog': () =>
    import('@/app/log/components/public/AlertRawLogWidget'),
} as const;
