'use client';

export type { NodeStatusWidgetProps } from '@/app/node-manager/components/public/NodeStatusWidget';

export const widgets = {
  'node.nodeStatus': () =>
    import('@/app/node-manager/components/public/NodeStatusWidget'),
} as const;
