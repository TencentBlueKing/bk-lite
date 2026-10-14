type CopyValues = Record<string, string | number>;
type Translate = (id: string, defaultMessage?: string, values?: CopyValues) => string;

const textId = (suffix: string) => `monitor.dashboards.text.${suffix}`;

/** 分类仪表盘文案。中文是缺词条时的回退，与 locales 中同 key 保持一致。 */
export const HOST_CATEGORY_COPY = {
  detailedMetrics: [textId('hostCategoryDetailedMetrics'), '详细指标'],
  swapUtilization: [textId('hostCategorySwapUtilization'), '交换使用率'],
  utilization: [textId('hostCategoryUtilization'), '使用率'],
  cpuUtilization: [textId('hostCategoryCpuUtilization'), 'CPU 使用率'],
  memoryUtilization: [textId('hostCategoryMemoryUtilization'), '内存使用率'],
  inboundThroughput: [textId('hostCategoryInboundThroughput'), '入站吞吐'],
  outboundThroughput: [textId('hostCategoryOutboundThroughput'), '出站吞吐'],
  inboundThroughputNamed: [textId('hostCategoryInboundThroughputNamed'), '入站吞吐 · {name}'],
  outboundThroughputNamed: [textId('hostCategoryOutboundThroughputNamed'), '出站吞吐 · {name}'],
  busiestNic: [textId('hostCategoryBusiestNic'), '吞吐最高网卡'],
  ioUtilization: [textId('hostCategoryIoUtilization'), 'I/O 利用率'],
  ioUtilizationNamed: [textId('hostCategoryIoUtilizationNamed'), 'I/O 利用率 · {name}'],
  perCoreCpuUtilization: [textId('hostCategoryPerCoreCpuUtilization'), 'CPU 分核使用率'],
  average: [textId('hostCategoryAverage'), '均值'],
  coreUtilizationNamed: [textId('hostCategoryCoreUtilizationNamed'), '{name} 使用率'],
  inodeUsage: [textId('hostCategoryInodeUsage'), 'Inode 使用率'],
  filesystemType: [textId('hostCategoryFilesystemType'), '文件系统类型'],
  diskPeak: [textId('hostCategoryDiskPeak'), '磁盘峰值'],
  diskUtilizationPeak: [textId('hostCategoryDiskUtilizationPeak'), '磁盘利用率（最高）'],
  chartFollowsSelection: [textId('hostCategoryChartFollowsSelection'), '选中后上图跟随'],
  cpuTimeBreakdown: [textId('hostCategoryCpuTimeBreakdown'), 'CPU 时间构成'],
  diskReadThroughput: [textId('hostCategoryDiskReadThroughput'), '磁盘读吞吐'],
  diskWriteThroughput: [textId('hostCategoryDiskWriteThroughput'), '磁盘写吞吐'],
  diskReadThroughputNamed: [textId('hostCategoryDiskReadThroughputNamed'), '磁盘读吞吐 · {name}'],
  diskWriteThroughputNamed: [textId('hostCategoryDiskWriteThroughputNamed'), '磁盘写吞吐 · {name}'],
  mountUsed: [textId('hostCategoryMountUsed'), '挂载用量%'],
  mountUsedNamed: [textId('hostCategoryMountUsedNamed'), '挂载用量% · {name}'],
  mounts: [textId('hostCategoryMounts'), '挂载点'],
  deviceRead: [textId('hostCategoryDeviceRead'), '设备读'],
  deviceWrite: [textId('hostCategoryDeviceWrite'), '设备写'],
  deviceReadNamed: [textId('hostCategoryDeviceReadNamed'), '设备读 · {name}'],
  deviceWriteNamed: [textId('hostCategoryDeviceWriteNamed'), '设备写 · {name}'],
  rwLatency: [textId('hostCategoryRwLatency'), '读写延迟'],
  rwLatencyNamed: [textId('hostCategoryRwLatencyNamed'), '读写延迟 · {name}'],
  readLatency: [textId('hostCategoryReadLatency'), '读延迟'],
  writeLatency: [textId('hostCategoryWriteLatency'), '写延迟'],
  relatedDevice: [textId('hostCategoryRelatedDevice'), '关联设备'],
  blockDevices: [textId('hostCategoryBlockDevices'), '块设备'],
  latencyReadWrite: [textId('hostCategoryLatencyReadWrite'), '延迟（读 / 写）'],
  noMountPoints: [textId('hostCategoryNoMountPoints'), '无挂载点数据'],
  noBlockDevices: [textId('hostCategoryNoBlockDevices'), '无磁盘设备数据'],
  uptime: [textId('hostCategoryUptime'), '运行时间'],
  packetRateInOut: [textId('hostCategoryPacketRateInOut'), '包速率（入/出）'],
  packetRateInOutNamed: [textId('hostCategoryPacketRateInOutNamed'), '包速率（入/出） · {name}'],
  inboundPacketRate: [textId('hostCategoryInboundPacketRate'), '入站包速率'],
  outboundPacketRate: [textId('hostCategoryOutboundPacketRate'), '出站包速率'],
  blockedProcesses: [textId('hostCategoryBlockedProcesses'), '阻塞进程'],
  zombieProcesses: [textId('hostCategoryZombieProcesses'), '僵尸进程'],
  busiestMount: [textId('hostCategoryBusiestMount'), '最满挂载点'],
  mountUsedOfTotal: [textId('hostCategoryMountUsedOfTotal'), '已用 {used} / 总量 {total}']
} as const;

export type HostCategoryCopyKey = keyof typeof HOST_CATEGORY_COPY;

export const hostCategoryText = (
  t: Translate,
  key: HostCategoryCopyKey,
  values?: CopyValues
) => {
  const [id, fallback] = HOST_CATEGORY_COPY[key];
  return t(id, fallback, values);
};
