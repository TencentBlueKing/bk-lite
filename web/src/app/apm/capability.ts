'use client';

export type { ServiceOverviewWidgetProps } from '@/app/apm/components/public/ServiceOverviewWidget';
export type { CallChainWidgetProps } from '@/app/apm/components/public/CallChainWidget';

export const widgets = {
  'apm.serviceOverview': () =>
    import('@/app/apm/components/public/ServiceOverviewWidget'),
  'apm.callChain': () =>
    import('@/app/apm/components/public/CallChainWidget'),
} as const;
