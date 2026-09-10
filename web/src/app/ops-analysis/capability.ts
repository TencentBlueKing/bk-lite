'use client';

export type { RelatedTopologyProps } from '@/app/ops-analysis/components/widgets/relatedTopology';

// 只登记加载器。禁止在本文件静态 import 业务组件，否则任意宿主探测本 App
// 都会打进所有画布（X6 / WebGL）。新组件同样写成 () => import(...)。
export const RelatedTopologyWidget = () =>
  import('@/app/ops-analysis/components/widgets/relatedTopology');
