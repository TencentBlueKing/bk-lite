/**
 * CPU 架构选项配置
 *
 * CE（社区版）默认仅支持 x86_64。
 * EE（企业版）通过 (enterprise) 目录覆盖，可额外支持 arm64 等架构。
 */

export interface CpuArchitectureOption {
  label: string;
  value: string;
}

/** CE 默认：采集器/控制器可选的 CPU 架构 */
const CE_COLLECTOR_CPU_ARCHITECTURE_OPTIONS: Record<string, CpuArchitectureOption[]> = {
  linux: [{ label: 'x86_64', value: 'x86_64' }],
  windows: [{ label: 'x86_64', value: 'x86_64' }],
};

/**
 * 获取当前版本支持的采集器 CPU 架构选项。
 * EE 覆盖文件路径: @/app/node-manager/(enterprise)/constants/cpuArchitecture
 */
const loadCollectorCpuArchitectureOptions = (): Record<string, CpuArchitectureOption[]> => {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod = require('@/app/node-manager/(enterprise)/constants/cpuArchitecture');
    return mod.COLLECTOR_CPU_ARCHITECTURE_OPTIONS || CE_COLLECTOR_CPU_ARCHITECTURE_OPTIONS;
  } catch {
    return CE_COLLECTOR_CPU_ARCHITECTURE_OPTIONS;
  }
};

export const COLLECTOR_CPU_ARCHITECTURE_OPTIONS = loadCollectorCpuArchitectureOptions();

export { CE_COLLECTOR_CPU_ARCHITECTURE_OPTIONS };
