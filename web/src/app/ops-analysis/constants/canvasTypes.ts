export type CanvasType =
  | 'dashboard'
  | 'topology'
  | 'architecture'
  | 'screen'
  | 'report';

export interface CanvasTypeMeta {
  type: CanvasType;
  objectType: CanvasType;
  endpoint: string;
  addLabelKey: string;
  editLabelKey: string;
  icon: 'dashboard' | 'topology' | 'architecture' | 'screen' | 'report';
}

export const CANVAS_TYPE_ORDER: CanvasType[] = [
  'dashboard',
  'topology',
  'architecture',
  'screen',
  'report',
];

export const CANVAS_TYPE_REGISTRY: Record<CanvasType, CanvasTypeMeta> = {
  dashboard: {
    type: 'dashboard',
    objectType: 'dashboard',
    endpoint: '/operation_analysis/api/dashboard/',
    addLabelKey: 'opsAnalysisSidebar.addDash',
    editLabelKey: 'opsAnalysisSidebar.editDash',
    icon: 'dashboard',
  },
  topology: {
    type: 'topology',
    objectType: 'topology',
    endpoint: '/operation_analysis/api/topology/',
    addLabelKey: 'opsAnalysisSidebar.addTopo',
    editLabelKey: 'opsAnalysisSidebar.editTopo',
    icon: 'topology',
  },
  architecture: {
    type: 'architecture',
    objectType: 'architecture',
    endpoint: '/operation_analysis/api/architecture/',
    addLabelKey: 'opsAnalysisSidebar.addArch',
    editLabelKey: 'opsAnalysisSidebar.editArch',
    icon: 'architecture',
  },
  screen: {
    type: 'screen',
    objectType: 'screen',
    endpoint: '/operation_analysis/api/screen/',
    addLabelKey: 'opsAnalysisSidebar.addScreen',
    editLabelKey: 'opsAnalysisSidebar.editScreen',
    icon: 'screen',
  },
  report: {
    type: 'report',
    objectType: 'report',
    endpoint: '/operation_analysis/api/report/',
    addLabelKey: 'opsAnalysisSidebar.addReport',
    editLabelKey: 'opsAnalysisSidebar.editReport',
    icon: 'report',
  },
};

export const CANVAS_TYPES = CANVAS_TYPE_ORDER;

export const isCanvasType = (type: unknown): type is CanvasType =>
  typeof type === 'string' && type in CANVAS_TYPE_REGISTRY;

export const getCanvasTypeMeta = (type: unknown): CanvasTypeMeta | null =>
  isCanvasType(type) ? CANVAS_TYPE_REGISTRY[type] : null;
