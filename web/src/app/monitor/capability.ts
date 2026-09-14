'use client';

export type { MonitorViewWidgetProps } from '@/app/monitor/components/public/MonitorViewWidget';
export type { AlertListWidgetProps } from '@/app/monitor/components/public/AlertListWidget';

export const widgets = {
  'monitor.monitorView': () =>
    import('@/app/monitor/components/public/MonitorViewWidget'),
  'monitor.alertList': () =>
    import('@/app/monitor/components/public/AlertListWidget'),
} as const;
