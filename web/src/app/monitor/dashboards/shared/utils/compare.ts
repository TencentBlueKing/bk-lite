import { PeriodCompare } from '../types';

export const getPeriodCompare = (currentValue: number, previousValue: number): PeriodCompare | null => {
  if (!Number.isFinite(currentValue) || !Number.isFinite(previousValue)) return null;
  if (previousValue === 0) {
    if (currentValue === 0) return { direction: 'flat', value: '0.0%' };
    // 上一周期为 0,百分比变化为无穷大、无意义,不展示对比徽章(避免误导性的固定 "100%")。
    return null;
  }
  const delta = ((currentValue - previousValue) / Math.abs(previousValue)) * 100;
  if (Math.abs(delta) < 0.05) return { direction: 'flat', value: '0.0%' };
  return {
    direction: delta > 0 ? 'up' : 'down',
    value: `${Math.abs(delta).toFixed(1)}%`
  };
};
