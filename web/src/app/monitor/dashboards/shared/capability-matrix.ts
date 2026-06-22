// 面向仪表盘的入口：把纯函数绑定到 codegen 生成的矩阵。
import {
  resolveCapability as resolveCapabilityCore,
  isMetricVisible,
  type CapabilityResolution,
  type ObjectType,
  type CapabilityKey
} from './capability-matrix-core';
import { CAPABILITY_MATRIX } from './capability-matrix.generated';

export function resolveCapability(objectType: ObjectType, idText: string): CapabilityResolution {
  return resolveCapabilityCore(CAPABILITY_MATRIX, objectType, idText);
}

export { isMetricVisible };
export type { CapabilityResolution, ObjectType, CapabilityKey };
