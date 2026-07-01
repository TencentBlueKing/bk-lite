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
  nameKey: string;
  addLabelKey: string;
  editLabelKey: string;
  descriptionKey: string;
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
    nameKey: 'opsAnalysisSidebar.dashboardType',
    addLabelKey: 'opsAnalysisSidebar.addDash',
    editLabelKey: 'opsAnalysisSidebar.editDash',
    descriptionKey: 'opsAnalysisSidebar.dashboardDesc',
    icon: 'dashboard',
  },
  topology: {
    type: 'topology',
    objectType: 'topology',
    endpoint: '/operation_analysis/api/topology/',
    nameKey: 'opsAnalysisSidebar.topologyType',
    addLabelKey: 'opsAnalysisSidebar.addTopo',
    editLabelKey: 'opsAnalysisSidebar.editTopo',
    descriptionKey: 'opsAnalysisSidebar.topologyDesc',
    icon: 'topology',
  },
  architecture: {
    type: 'architecture',
    objectType: 'architecture',
    endpoint: '/operation_analysis/api/architecture/',
    nameKey: 'opsAnalysisSidebar.architectureType',
    addLabelKey: 'opsAnalysisSidebar.addArch',
    editLabelKey: 'opsAnalysisSidebar.editArch',
    descriptionKey: 'opsAnalysisSidebar.architectureDesc',
    icon: 'architecture',
  },
  screen: {
    type: 'screen',
    objectType: 'screen',
    endpoint: '/operation_analysis/api/screen/',
    nameKey: 'opsAnalysisSidebar.screenType',
    addLabelKey: 'opsAnalysisSidebar.addScreen',
    editLabelKey: 'opsAnalysisSidebar.editScreen',
    descriptionKey: 'opsAnalysisSidebar.screenDesc',
    icon: 'screen',
  },
  report: {
    type: 'report',
    objectType: 'report',
    endpoint: '/operation_analysis/api/report/',
    nameKey: 'opsAnalysisSidebar.reportType',
    addLabelKey: 'opsAnalysisSidebar.addReport',
    editLabelKey: 'opsAnalysisSidebar.editReport',
    descriptionKey: 'opsAnalysisSidebar.reportDesc',
    icon: 'report',
  },
};

export const CANVAS_TYPES = CANVAS_TYPE_ORDER;

export const isCanvasType = (type: unknown): type is CanvasType =>
  typeof type === 'string' && type in CANVAS_TYPE_REGISTRY;

export const getCanvasTypeMeta = (type: unknown): CanvasTypeMeta | null =>
  isCanvasType(type) ? CANVAS_TYPE_REGISTRY[type] : null;
