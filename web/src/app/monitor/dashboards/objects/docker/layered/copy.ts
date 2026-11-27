type CopyValues = Record<string, string | number>;
type Translate = (id: string, defaultMessage?: string, values?: CopyValues) => string;

const textId = (suffix: string) => `monitor.dashboards.text.${suffix}`;

export const DOCKER_COPY = {
  tabOverview: [textId('dockerCategoryTabOverview'), '概览'],
  tabContainers: [textId('dockerCategoryTabContainers'), '容器'],
  sectionOverview: [textId('dockerCategorySectionOverview'), '概览'],
  sectionResources: [textId('dockerCategorySectionResources'), '容器资源'],
  sectionInventory: [textId('dockerCategorySectionInventory'), '容器清单'],
  kpiAlerts: [textId('dockerCategoryKpiAlerts'), '告警数量'],
  kpiRunning: [textId('dockerCategoryKpiRunning'), '运行中的容器'],
  kpiStopped: [textId('dockerCategoryKpiStopped'), '已停止的容器'],
  kpiTotal: [textId('dockerCategoryKpiTotal'), '容器总数'],
  kpiShare: [textId('dockerCategoryKpiShare'), '停止占比'],
  alertHint: [textId('dockerCategoryAlertHint'), '当前对象相关的告警条数，可打开告警列表。'],
  runningHint: [textId('dockerCategoryRunningHint'), '这台主机上，Docker 引擎报告的正在运行的容器个数。'],
  stoppedHint: [textId('dockerCategoryStoppedHint'), '这台主机上，Docker 引擎计入的非运行且非暂停容器个数。这一项不是 exited 容器的条数，创建未启动或已死亡的容器也会算进来。'],
  totalHint: [textId('dockerCategoryTotalHint'), '这台主机上，Docker 引擎报告的容器个数。'],
  shareHint: [textId('dockerCategoryShareHint'), '已停止容器占容器总数的比例，用来看出主机上容器构成，不是健康评分。'],
  shareEmpty: [textId('dockerCategoryShareEmpty'), '还没有采到总数，或总数为 0 时显示 —。'],
  cpuTitle: [textId('dockerCategoryCpuTitle'), '容器 CPU 占用率'],
  cpuHint: [textId('dockerCategoryCpuHint'), '该容器占用的 CPU，按宿主机可用算力计算。分配了多核配额时，这个值可以超过 100%。'],
  memPercentTitle: [textId('dockerCategoryMemPercentTitle'), '容器内存使用率'],
  memPercentHint: [textId('dockerCategoryMemPercentHint'), '该容器已用内存占其可用上限的百分比。'],
  memBytesTitle: [textId('dockerCategoryMemBytesTitle'), '容器内存使用量'],
  memBytesHint: [textId('dockerCategoryMemBytesHint'), '该容器当前实际占用的内存。'],
  restartTitle: [textId('dockerCategoryRestartTitle'), '重启次数'],
  restartHint: [textId('dockerCategoryRestartHint'), '该容器当前记录的重启次数。这是当前值，不是一段时间里新增加的次数。'],
  inventoryHint: [textId('dockerCategoryInventoryHint'), '本表列出当前采到资源数据的容器。'],
  columnName: [textId('dockerCategoryColumnName'), '容器名'],
  empty: [textId('dockerCategoryEmpty'), '暂无数据'],
  clearSelection: [textId('dockerCategoryClearSelection'), '清空'],
  collectionNotConnected: [textId('dockerCategoryCollectionNotConnected'), '尚未接入采集'],
  collectionUnknown: [textId('dockerCategoryCollectionUnknown'), '未知'],
  collectionExpired: [textId('dockerCategoryCollectionExpired'), '已过期'],
  collectionFailed: [textId('dockerCategoryCollectionFailed'), '采集失败'],
  collectionSuccess: [textId('dockerCategoryCollectionSuccess'), '采集成功'],
  alertDrawerTitle: [textId('dockerCategoryAlertDrawerTitle'), '告警'],
  alertDrawerEmpty: [textId('dockerCategoryAlertDrawerEmpty'), '当前没有相关告警'],
  alertDrawerEmptyHint: [textId('dockerCategoryAlertDrawerEmptyHint'), '打开后可以查看这个对象的告警列表。'],
  alertDrawerFooter: [textId('dockerCategoryAlertDrawerFooter'), '列表里是当前对象尚未恢复的告警。']
} as const;

export type DockerCopyKey = keyof typeof DOCKER_COPY;

export const dockerText = (t: Translate, key: DockerCopyKey): string => {
  const [id, fallback] = DOCKER_COPY[key];
  return t(id, fallback);
};
