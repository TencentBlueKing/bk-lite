import { describe, expect, it } from 'vitest';
import { customPluginTargetOptions, isCustomPluginTargetModel } from '../targetModel';

const models = [
  { label: 'K8S Cluster', value: 'k8s_cluster' },
  { label: 'K8S Namespace', value: 'k8s_namespace' },
  { label: 'K8S Workload', value: 'k8s_workload' },
  { label: 'K8S Node', value: 'k8s_node' },
  { label: 'K8S Pod', value: 'k8s_pod' },
  { label: 'Docker', value: 'docker' },
  { label: '主机', value: 'host' },
];

describe('自定义插件目标模型', () => {
  it('新建时不提供 K8S 分类下的模型', () => {
    expect(isCustomPluginTargetModel('k8s_cluster')).toBe(false);
    expect(isCustomPluginTargetModel('k8s_pod')).toBe(false);
    expect(isCustomPluginTargetModel('docker')).toBe(true);
    expect(isCustomPluginTargetModel('host')).toBe(true);
    expect(customPluginTargetOptions(models).map((item) => item.value)).toEqual(['docker', 'host']);
  });

  it('编辑已有 K8S 插件时仍保留当前模型，避免下拉空白', () => {
    expect(customPluginTargetOptions(models, 'k8s_namespace').map((item) => item.value)).toEqual([
      'k8s_namespace',
      'docker',
      'host',
    ]);
  });
});
