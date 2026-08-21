// @vitest-environment node
import { describe, expect, it } from 'vitest';

import {
  buildIntegrationConfigureUrl,
  parseIntegrationObjectId,
  resolveIntegrationEntryContext
} from '../integrationEntryContext';

describe('集成入口上下文', () => {
  it('直接使用插件目录返回的权威对象上下文', () => {
    const result = resolveIntegrationEntryContext(
      {
        id: 297,
        name: 'K8S',
        display_name: 'Kubernetes',
        display_description: '集群监控',
        template_type: 'builtin',
        parent_monitor_object: 12,
        parent_monitor_object_name: 'Cluster',
        parent_monitor_object_icon: 'mm-k8s_K8S'
      },
      []
    );

    expect(result).toEqual({
      ok: true,
      context: {
        objectId: '12',
        objectName: 'Cluster',
        objectIcon: 'mm-k8s_K8S',
        pluginId: '297',
        pluginName: 'K8S',
        pluginDisplayName: 'Kubernetes',
        pluginDescription: '集群监控',
        templateType: 'builtin'
      }
    });
  });

  it('兼容旧接口仅返回父对象 ID 的情况', () => {
    const result = resolveIntegrationEntryContext(
      { id: 297, name: 'K8S', parent_monitor_object: '12' },
      [{ id: 12, name: 'Cluster', icon: 'cluster-icon' }]
    );

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.context.objectName).toBe('Cluster');
      expect(result.context.objectIcon).toBe('cluster-icon');
    }
  });

  it('缺少父对象时拒绝生成带空 id 和 name 的地址', () => {
    expect(resolveIntegrationEntryContext({ id: 297, name: 'K8S' }, [])).toEqual(
      { ok: false, reason: 'missing-parent-object' }
    );
  });

  it('生成完整配置地址', () => {
    const result = resolveIntegrationEntryContext(
      {
        id: 297,
        name: 'K8S',
        template_type: 'builtin',
        parent_monitor_object: 12,
        parent_monitor_object_name: 'Cluster'
      },
      []
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;

    const url = buildIntegrationConfigureUrl(result.context, 'default-icon');
    const params = new URL(url, 'https://example.test').searchParams;
    expect(params.get('id')).toBe('12');
    expect(params.get('name')).toBe('Cluster');
    expect(params.get('plugin_name')).toBe('K8S');
    expect(params.get('plugin_id')).toBe('297');
  });

  it.each([
    [undefined, undefined],
    ['', undefined],
    ['0', undefined],
    ['abc', undefined],
    ['12', 12]
  ])('规范化对象 ID %s', (value, expected) => {
    expect(parseIntegrationObjectId(value)).toBe(expected);
  });
});
