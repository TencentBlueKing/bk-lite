'use client';

export type { MonitorViewWidgetProps } from '@/app/monitor/components/public/MonitorViewWidget';
export type { AlertListWidgetProps } from '@/app/monitor/components/public/AlertListWidget';
export type { MonitorPolicyWidgetProps } from '@/app/monitor/components/public/MonitorPolicyWidget';

export const widgets = {
  'monitor.monitorView': () =>
    import('@/app/monitor/components/public/MonitorViewWidget'),
  'monitor.alertList': () =>
    import('@/app/monitor/components/public/AlertListWidget'),
  'monitor.monitorPolicy': () =>
    import('@/app/monitor/components/public/MonitorPolicyWidget'),
} as const;
