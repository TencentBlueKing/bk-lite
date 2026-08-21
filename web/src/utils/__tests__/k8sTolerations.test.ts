import { describe, expect, it } from 'vitest';
import {
  DEFAULT_K8S_DS_TOLERATIONS,
  isValidK8sTolerations,
  k8sTolerationModeFromValue,
  k8sTolerationsFromMode,
  normalizeK8sTolerations
} from '../k8sTolerations';

describe('K8s DaemonSet tolerations', () => {
  it('treats null as unset default', () => {
    expect(isValidK8sTolerations(null)).toBe(true);
    expect(normalizeK8sTolerations(null)).toBeNull();
    expect(k8sTolerationModeFromValue(null)).toBe('default');
    expect(k8sTolerationsFromMode('default')).toBeNull();
  });

  it('keeps an explicit empty list as zero tolerations', () => {
    expect(isValidK8sTolerations([])).toBe(true);
    expect(normalizeK8sTolerations([])).toEqual([]);
    expect(k8sTolerationModeFromValue([])).toBe('none');
    expect(k8sTolerationsFromMode('none')).toEqual([]);
  });

  it('accepts custom Equal and Exists items', () => {
    const custom = [
      { key: 'dedicated', value: 'edge', effect: 'NoSchedule' },
      { key: 'CriticalAddonsOnly', effect: 'NoExecute' }
    ];
    expect(isValidK8sTolerations(custom)).toBe(true);
    expect(normalizeK8sTolerations(custom)).toEqual(custom);
    expect(k8sTolerationModeFromValue(custom)).toBe('custom');
    expect(k8sTolerationsFromMode('custom', custom)).toEqual(custom);
  });

  it('accepts the product default pair', () => {
    expect(isValidK8sTolerations(DEFAULT_K8S_DS_TOLERATIONS)).toBe(true);
  });

  it.each([
    { key: 'dedicated', effect: 'NoSchedule' },
    [{ operator: 'Exists', effect: 'NoSchedule' }],
    [{ key: '', effect: 'NoSchedule' }],
    [{ key: 'dedicated', effect: 'PreferNoSchedule' }],
    [{ key: 'a', value: 'X__DS_TOLERATIONS__X', effect: 'NoSchedule' }],
    [{ key: 'dedicated', effect: 'NoSchedule', operator: 'Equal' }],
    Array.from({ length: 17 }, () => ({
      key: 'dedicated',
      effect: 'NoSchedule'
    }))
  ])('rejects %j', (value) => {
    expect(isValidK8sTolerations(value)).toBe(false);
  });
});
