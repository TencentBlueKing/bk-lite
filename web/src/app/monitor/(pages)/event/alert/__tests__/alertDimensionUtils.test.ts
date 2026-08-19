// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { buildAlertDimensionDisplayItems } from '../alertDimensionUtils';

describe('告警详情维度展示模型', () => {
  it('按指标定义顺序展示 description 与告警值', () => {
    expect(
      buildAlertDimensionDisplayItems(
        [
          { name: 'device', description: '设备' },
          { name: 'interface', description: '接口' }
        ],
        { interface: 'GigabitEthernet0/1', device: 'switch-01' }
      )
    ).toEqual([
      { key: 'device', label: '设备', value: 'switch-01' },
      {
        key: 'interface',
        label: '接口',
        value: 'GigabitEthernet0/1'
      }
    ]);
  });

  it('description 为空白时回退到维度名', () => {
    expect(
      buildAlertDimensionDisplayItems(
        [{ name: 'pod_name', description: '   ' }],
        { pod_name: 'api-7db9' }
      )
    ).toEqual([{ key: 'pod_name', label: 'pod_name', value: 'api-7db9' }]);
  });

  it('把额外实际维度按 key 排序后追加到指标定义维度之后', () => {
    expect(
      buildAlertDimensionDisplayItems(
        [{ name: 'device', description: '设备' }],
        { zone: 'cn-north', device: 'switch-01', rack: 'A-03' }
      )
    ).toEqual([
      { key: 'device', label: '设备', value: 'switch-01' },
      { key: 'rack', label: 'rack', value: 'A-03' },
      { key: 'zone', label: 'zone', value: 'cn-north' }
    ]);
  });

  it('告警维度字典为空时返回空列表', () => {
    expect(
      buildAlertDimensionDisplayItems(
        [{ name: 'device', description: '设备' }],
        {}
      )
    ).toEqual([]);
  });

  it('非空告警字典缺少已定义维度时用 -- 展示', () => {
    expect(
      buildAlertDimensionDisplayItems(
        [
          { name: 'device', description: '设备' },
          { name: 'interface', description: '接口' }
        ],
        { device: 'switch-01' }
      )
    ).toEqual([
      { key: 'device', label: '设备', value: 'switch-01' },
      { key: 'interface', label: '接口', value: '--' }
    ]);
  });

  it('缺失 metric 定义时安全展示实际维度', () => {
    expect(
      buildAlertDimensionDisplayItems(undefined, {
        zone: 'cn-north',
        device: 'switch-01'
      })
    ).toEqual([
      { key: 'device', label: 'device', value: 'switch-01' },
      { key: 'zone', label: 'zone', value: 'cn-north' }
    ]);
  });

  it('维度值为空字符串时用 -- 展示', () => {
    expect(
      buildAlertDimensionDisplayItems(
        [{ name: 'interface', description: '接口' }],
        { interface: '' }
      )
    ).toEqual([{ key: 'interface', label: '接口', value: '--' }]);
  });

  it('历史告警缺少 dimensions 字段时返回空列表', () => {
    expect(buildAlertDimensionDisplayItems([], undefined)).toEqual([]);
  });
});
