'use client';

export type { RelatedTopologyProps } from '@/app/ops-analysis/components/widgets/relatedTopology';
export type { NetworkStatusTopologyEmbedProps } from '@/app/ops-analysis/components/widgets/networkStatusTopology/embed';
export type { Application3DEmbedProps } from '@/app/ops-analysis/components/widgets/application3D/embed';

// 只登记加载器。禁止在本文件静态 import 业务组件，否则任意宿主探测本 App
// 都会打进所有画布（X6 / WebGL）。新组件同样写成 () => import(...)。
export const widgets = {
  'ops-analysis.relatedTopology': () =>
    import('@/app/ops-analysis/components/widgets/relatedTopology'),
  'ops-analysis.networkStatusTopology': () =>
    import('@/app/ops-analysis/components/widgets/networkStatusTopology/embed'),
  'ops-analysis.application3D': () =>
    import('@/app/ops-analysis/components/widgets/application3D/embed'),
} as const;
