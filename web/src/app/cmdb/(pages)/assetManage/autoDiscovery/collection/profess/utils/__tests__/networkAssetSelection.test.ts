import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  NETWORK_COLLECTION_ASSET_MODELS,
  findDuplicateNetworkAssetIp,
  mergeNetworkAssetSearchPages,
  mergeVisibleNetworkAssetSelection,
} from '../networkAssetSelection';

const switchA = {
  inst_uuid: '63e4a531-b6bb-43cc-9eae-8eb8a09f795e',
  model_id: 'switch',
  inst_name: 'sw-a',
  ip_addr: '10.0.0.1',
};
const switchC = {
  inst_uuid: '7f1d3c20-0b11-4a8c-9e3a-21d4b6c8e901',
  model_id: 'switch',
  inst_name: 'sw-c',
  ip_addr: '10.0.0.3',
};
const routerB = {
  inst_uuid: '4c6643d2-4dc5-4a2a-8f24-3af72f33f7bc',
  model_id: 'router',
  inst_name: 'rt-b',
  ip_addr: '10.0.0.2',
};

describe('Network 跨模型资产选择', () => {
  it('允许模型恰好是交换机、路由器、防火墙和负载均衡', () => {
    expect([...NETWORK_COLLECTION_ASSET_MODELS]).toEqual([
      'switch',
      'router',
      'firewall',
      'loadbalance',
    ]);
  });

  it('确认时保留未出现在当前页的已选实例，并去掉当前页取消勾选的实例', () => {
    expect(
      mergeVisibleNetworkAssetSelection({
        previouslySelected: [routerB, switchA],
        visibleInstUuids: [switchA.inst_uuid],
        checkedRows: [switchC],
      })
    ).toEqual([routerB, switchC]);
  });

  it('同一 inst_uuid 不会重复加入已选列表', () => {
    expect(
      mergeVisibleNetworkAssetSelection({
        previouslySelected: [routerB],
        visibleInstUuids: [routerB.inst_uuid],
        checkedRows: [routerB, routerB],
      })
    ).toEqual([routerB]);
  });

  it('管理 IP 相同视为重复', () => {
    expect(
      findDuplicateNetworkAssetIp([
        switchA,
        { ...routerB, ip_addr: '10.0.0.1' },
      ])
    ).toBe('10.0.0.1');
  });

  it('管理 IP 比较忽略首尾空白', () => {
    expect(
      findDuplicateNetworkAssetIp([
        switchA,
        { ...routerB, ip_addr: ' 10.0.0.1 ' },
      ])
    ).toBe('10.0.0.1');
  });

  it('按模型查询顺序拼接搜索页，总数为 count 之和', () => {
    expect(
      mergeNetworkAssetSearchPages([
        { insts: [switchA], count: 2 },
        { insts: [routerB], count: 3 },
      ])
    ).toEqual({
      insts: [switchA, routerB],
      count: 5,
    });
  });

  it('未勾选模型时搜索结果为空', () => {
    expect(mergeNetworkAssetSearchPages([])).toEqual({ insts: [], count: 0 });
  });

  it('选择资产抽屉按父容器铺满表格，避免 100vh 裁掉总数和分页', () => {
    const root = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(
      resolve(root, '../../components/baseTask.tsx'),
      'utf8'
    );
    expect(/scroll=\{\{\s*y:\s*['"]calc\(100vh/.test(source)).toBe(false);
    expect(source).toMatch(/display:\s*'flex'/);
    expect(source).toMatch(/flexDirection:\s*'column'/);
    expect(source).toMatch(/overflow:\s*'hidden'/);
    expect(source).toMatch(
      /min-h-0 h-full flex-1 overflow-hidden[\s\S]*<CustomTable/
    );
  });

  it('中英文都有对象类型、设备模型多选和重复 IP 文案', () => {
    const root = dirname(fileURLToPath(import.meta.url));
    const zh = JSON.parse(
      readFileSync(resolve(root, '../../../../../../../locales/zh.json'), 'utf8')
    );
    const en = JSON.parse(
      readFileSync(resolve(root, '../../../../../../../locales/en.json'), 'utf8')
    );
    for (const locale of [zh, en]) {
      expect(locale.Collection.objectType).toBeTruthy();
      expect(locale.Collection.selectDeviceModels).toBeTruthy();
      expect(locale.Collection.selectDeviceModelsPlaceholder).toBeTruthy();
      expect(locale.Collection.duplicateManageIp).toContain('{ip}');
    }
  });
});
