import { describe, expect, it } from 'vitest';

import {
  mergeInstSelection,
  resolveInstFetchModelId,
  resolveInstPaginationChange,
  restoreInstDrawerSelection,
} from '../instAssetPicker';

describe('选择资产分页', () => {
  it('切换页码时保留当前每页条数，而不是回到 10', () => {
    expect(
      resolveInstPaginationChange({
        currentPageSize: 50,
        nextPage: 3,
        nextPageSize: 50,
      })
    ).toEqual({ page: 3, pageSize: 50 });
  });

  it('切换每页条数时回到第 1 页，并记下新的 pageSize', () => {
    expect(
      resolveInstPaginationChange({
        currentPageSize: 10,
        nextPage: 4,
        nextPageSize: 50,
      })
    ).toEqual({ page: 1, pageSize: 50 });
  });

  it('页码回调没带 pageSize 时继续用当前每页条数', () => {
    expect(
      resolveInstPaginationChange({
        currentPageSize: 50,
        nextPage: 2,
        nextPageSize: 0,
      })
    ).toEqual({ page: 2, pageSize: 50 });
  });
});

describe('选择资产勾选', () => {
  it('翻页后继续勾选时，保留其他页已经选中的资产', () => {
    const previousSelectedRows = [{ inst_uuid: 'page1-a', inst_name: 'A' }];
    const currentPageRows = [
      { inst_uuid: 'page2-b', inst_name: 'B' },
      { inst_uuid: 'page2-c', inst_name: 'C' },
    ];

    expect(
      mergeInstSelection({
        currentPageRows,
        selectedRowKeys: ['page1-a', 'page2-b'],
        previousSelectedRows,
      })
    ).toEqual([
      { inst_uuid: 'page1-a', inst_name: 'A' },
      { inst_uuid: 'page2-b', inst_name: 'B' },
    ]);
  });

  it('取消当前页勾选时，不影响其他页已选项', () => {
    const previousSelectedRows = [
      { inst_uuid: 'page1-a', inst_name: 'A' },
      { inst_uuid: 'page2-b', inst_name: 'B' },
    ];
    const currentPageRows = [
      { inst_uuid: 'page2-b', inst_name: 'B' },
      { inst_uuid: 'page2-c', inst_name: 'C' },
    ];

    expect(
      mergeInstSelection({
        currentPageRows,
        selectedRowKeys: ['page1-a'],
        previousSelectedRows,
      })
    ).toEqual([{ inst_uuid: 'page1-a', inst_name: 'A' }]);
  });

  it('重新打开抽屉时，按已确认资产恢复勾选，而不是只恢复当前页交集', () => {
    expect(
      restoreInstDrawerSelection([
        { inst_uuid: 'page1-a', inst_name: 'A' },
        { inst_uuid: 'page3-z', inst_name: 'Z' },
      ])
    ).toEqual({
      selectedKeys: ['page1-a', 'page3-z'],
      selectedRows: [
        { inst_uuid: 'page1-a', inst_name: 'A' },
        { inst_uuid: 'page3-z', inst_name: 'Z' },
      ],
    });
  });
});

describe('选择资产请求模型', () => {
  it('通用选资产任务按实例模型拉取，避免翻页时改用采集模型', () => {
    expect(
      resolveInstFetchModelId({
        isCommonSelectInstTask: true,
        instanceModelId: 'host',
        collectionModelId: 'os',
        relateType: 'network',
      })
    ).toBe('host');
  });

  it('网络设备下拉选择时按当前 relateType 拉取', () => {
    expect(
      resolveInstFetchModelId({
        isCommonSelectInstTask: false,
        instanceModelId: 'host',
        collectionModelId: 'os',
        relateType: 'network',
      })
    ).toBe('network');
  });
});
