'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useMemo,
  useRef,
} from 'react';
import { Button, Input, Tabs, Tree } from 'antd';
import OperateModal from '@/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import { convertGroupTreeToTreeSelectData } from '@/utils';
import CustomTable from '@/components/custom-table';
import {
  ColumnItem,
  ModalRef,
  ModalConfig,
  TabItem,
  Pagination,
  TableDataItem,
  ObjectItem,
  MetricItem,
} from '@/app/monitor/types';
import { CloseOutlined } from '@ant-design/icons';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import selectInstanceStyle from './selectInstance.module.scss';
import { showInstName } from '@/app/monitor/utils/common';
import { useUserInfoContext } from '@/context/userInfo';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import {
  DEFAULT_VIEW_FIXED_FIELD_KEYS,
  resolveViewColumns,
} from '@/app/monitor/(pages)/view/viewColumnPreference';
import { buildInstanceViewColumns } from '@/app/monitor/(pages)/view/instanceViewColumns';

const filterTreeData = (treeData: any, searchText: string) => {
  if (!searchText) return treeData;
  return treeData
    .map((item: any) => {
      const { title, children } = item;
      if (title.toLowerCase().includes(searchText.toLowerCase())) {
        return item;
      }
      if (children) {
        const filteredChildren = filterTreeData(children, searchText);
        if (filteredChildren.length > 0) {
          return {
            ...item,
            children: filteredChildren,
          };
        }
      }
      return null;
    })
    .filter((item: any) => item !== null);
};

const getLabelByKey = (key: string | number, treeData: any): string => {
  const target = String(key);
  for (const node of treeData) {
    // 组织树 key 为 number，勾选回调/状态里可能是 string，须归一化
    if (String(node.key) === target) {
      return node.title;
    }
    if (node.children?.length) {
      const foundLabel = getLabelByKey(key, node.children);
      if (foundLabel) return foundLabel;
    }
  }
  return '';
};

const SelectAssets = forwardRef<ModalRef, ModalConfig>(
  ({ onSuccess, monitorObject, objects }, ref) => {
    const { t } = useTranslation();
    const { getInstanceList, getMonitorMetrics } = useMonitorApi();
    const { getViewColumnPreference } = useViewApi();
    const { convertToLocalizedTime } = useLocalizedTime();
    const { getEnumValueUnit } = useUnitTransform();
    const { groupTree } = useUserInfoContext();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [pagination, setPagination] = useState<Pagination>({
      current: 1,
      total: 0,
      pageSize: 20,
    });
    const [activeTab, setActiveTab] = useState<string>('instance');
    const isInstance = activeTab === 'instance';
    const [title, setTitle] = useState<string>('');
    const [tableLoading, setTableLoading] = useState<boolean>(false);
    const [selectedRowKeys, setSelectedRowKeys] = useState<Array<string>>([]);
    const [tableData, setTableData] = useState<TableDataItem[]>([]);
    const [searchText, setSearchText] = useState<string>('');
    const [selectedTreeKeys, setSelectedTreeKeys] = useState<string[]>([]);
    const [treeSearchText, setTreeSearchText] = useState<string>('');
    const [rowId, setRowId] = useState<number>(0);
    const [instanceSelectedKeys, setInstanceSelectedKeys] = useState<string[]>(
      []
    );
    const [organizationSelectedKeys, setOrganizationSelectedKeys] = useState<
      string[]
    >([]);
    const [metrics, setMetrics] = useState<MetricItem[]>([]);
    const [columnPreference, setColumnPreference] = useState<string[] | null>(
      null
    );
    const [fixedColumnPreference, setFixedColumnPreference] = useState<
      string[] | null
    >(null);
    const [selectedLabelMap, setSelectedLabelMap] = useState<
      Record<string, string>
    >({});
    const paginationRef = useRef(pagination);
    const searchTextRef = useRef(searchText);
    paginationRef.current = pagination;
    searchTextRef.current = searchText;

    const objectItem = useMemo(
      () =>
        (objects as ObjectItem[])?.find(
          (item: ObjectItem) => item.id === Number(monitorObject as React.Key)
        ) || ({} as ObjectItem),
      [objects, monitorObject]
    );

    const tabs: TabItem[] = [
      {
        label: t('monitor.asset'),
        key: 'instance',
      },
      {
        label: t('monitor.group'),
        key: 'organization',
      },
    ];

    const tableColumn = useMemo(
      () =>
        buildInstanceViewColumns({
          objects: (objects as ObjectItem[]) || [],
          targetObject: objectItem,
          t,
          convertToLocalizedTime,
          metrics,
          getEnumValueUnit,
          objectId: monitorObject as React.Key,
          includeDimensionTooltip: false,
        }),
      [
        objects,
        objectItem,
        t,
        convertToLocalizedTime,
        metrics,
        getEnumValueUnit,
        monitorObject,
      ]
    );

    const columns = useMemo(
      () =>
        resolveViewColumns(
          tableColumn,
          columnPreference,
          [],
          fixedColumnPreference,
          DEFAULT_VIEW_FIXED_FIELD_KEYS
        ).columns as ColumnItem[],
      [tableColumn, columnPreference, fixedColumnPreference]
    );

    const treeData = useMemo(() => {
      return convertGroupTreeToTreeSelectData(groupTree);
    }, [groupTree]);

    const filteredTreeData = useMemo(() => {
      return filterTreeData(treeData, treeSearchText);
    }, [treeData, treeSearchText]);

    const mergeSelectedLabels = (rows: TableDataItem[]) => {
      setSelectedLabelMap((prev) => {
        const next = { ...prev };
        rows.forEach((row) => {
          if (row?.instance_id) {
            next[String(row.instance_id)] = showInstName(objectItem, row);
          }
        });
        return next;
      });
    };

    /** 编辑回填 / 跨页已选：按存储键精确拉取展示名，避免侧栏长期显示 raw instance_id。 */
    const hydrateSelectedLabels = async (keys: string[]) => {
      const uniqueKeys = [...new Set(keys.filter(Boolean))];
      if (!uniqueKeys.length) return;
      const results = await Promise.all(
        uniqueKeys.map(async (instanceId) => {
          try {
            const data = await getInstanceList(monitorObject as React.Key, {
              page: 1,
              page_size: 1,
              instance_id: instanceId,
              add_metrics: false,
            });
            return data?.results?.[0] as TableDataItem | undefined;
          } catch {
            return undefined;
          }
        })
      );
      mergeSelectedLabels(
        results.filter(Boolean) as TableDataItem[]
      );
    };

    const fetchColumns = async () => {
      const objectId = monitorObject as React.Key;
      const displayMetricNames = (objectItem?.display_fields || [])
        .flatMap((column) => column.metrics || [])
        .map((binding) => binding.metric)
        .filter(Boolean);
      const [metricRes, preference] = await Promise.all([
        getMonitorMetrics({
          monitor_object_id: String(objectId),
          ...(displayMetricNames.length
            ? { name_in: [...new Set(displayMetricNames)].join(',') }
            : {}),
        }).catch(() => ({ items: [] })),
        getViewColumnPreference(objectId).catch(() => null),
      ]);
      setMetrics(metricRes?.items || []);
      setColumnPreference(preference?.field_keys || null);
      setFixedColumnPreference(
        preference == null
          ? null
          : Array.isArray(preference.fixed_field_keys)
            ? preference.fixed_field_keys
            : null
      );
    };

    const fetchData = async (
      page = paginationRef.current.current,
      pageSize = paginationRef.current.pageSize,
      name = searchTextRef.current
    ) => {
      try {
        setTableLoading(true);
        const data = await getInstanceList(monitorObject as React.Key, {
          page,
          page_size: pageSize,
          name: name || '',
          add_metrics: true,
        });
        const results = data?.results || [];
        setTableData(results);
        mergeSelectedLabels(results);
        setPagination((prev) => ({
          ...prev,
          current: page,
          pageSize,
          total: data?.count || 0,
        }));
      } finally {
        setTableLoading(false);
      }
    };

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form: { type, values, id } }) => {
        setPagination((prev: Pagination) => ({
          ...prev,
          current: 1,
        }));
        paginationRef.current = {
          ...paginationRef.current,
          current: 1,
        };
        setTableData([]);
        setSearchText('');
        searchTextRef.current = '';
        setGroupVisible(true);
        setTitle(title);
        setRowId(id as number);
        setActiveTab((type as string) || 'instance');
        if (type === 'instance' || !type) {
          const selected = (values as string[]) || [];
          setInstanceSelectedKeys(selected);
          setSelectedRowKeys(selected);
          setSelectedLabelMap({});
          void fetchColumns();
          void fetchData(1, paginationRef.current.pageSize, '');
          void hydrateSelectedLabels(selected);
        } else {
          setOrganizationSelectedKeys((values as string[]) || []);
          setSelectedTreeKeys((values as string[]) || []);
        }
      },
    }));

    const changeTab = (val: string) => {
      setActiveTab(val);
      if (val === 'instance') {
        setSelectedRowKeys(instanceSelectedKeys);
        setPagination((prev) => ({
          ...prev,
          current: 1,
        }));
        paginationRef.current = {
          ...paginationRef.current,
          current: 1,
        };
        if (!tableData.length) {
          void fetchColumns();
          void fetchData(1, paginationRef.current.pageSize);
        }
        return;
      }
      setSelectedTreeKeys(organizationSelectedKeys);
    };

    const onSelectChange = (selectedKeys: any) => {
      const currentPageKeys = tableData.map((item) => item.instance_id);
      const otherPagesSelectedKeys = instanceSelectedKeys.filter(
        (key) => !currentPageKeys.includes(key)
      );
      const newSelectedKeys = [...otherPagesSelectedKeys, ...selectedKeys];
      setSelectedRowKeys(newSelectedKeys);
      setInstanceSelectedKeys(newSelectedKeys);
      mergeSelectedLabels(
        tableData.filter((item) => selectedKeys.includes(item.instance_id))
      );
    };

    const rowSelection = {
      selectedRowKeys: selectedRowKeys.filter((key) =>
        tableData.some((item) => item.instance_id === key)
      ),
      onChange: onSelectChange,
    };

    const handleSubmit = async () => {
      handleCancel();
      onSuccess?.(
        {
          type: activeTab,
          values: activeTab === 'instance' ? selectedRowKeys : selectedTreeKeys,
        },
        rowId
      );
    };

    const handleCancel = () => {
      setGroupVisible(false);
      setSelectedRowKeys([]);
      setSelectedTreeKeys([]);
      setInstanceSelectedKeys([]);
      setOrganizationSelectedKeys([]);
      setSearchText('');
      searchTextRef.current = '';
      setTreeSearchText('');
      setTableData([]);
      setSelectedLabelMap({});
    };

    const handleTableChange = (nextPagination: Pagination) => {
      paginationRef.current = {
        ...paginationRef.current,
        ...nextPagination,
      };
      void fetchData(
        nextPagination.current,
        nextPagination.pageSize,
        searchTextRef.current
      );
    };

    const handleSearch = () => {
      paginationRef.current = {
        ...paginationRef.current,
        current: 1,
      };
      setPagination((prev) => ({ ...prev, current: 1 }));
      void fetchData(1, paginationRef.current.pageSize, searchTextRef.current);
    };

    const handleClearSelection = () => {
      if (activeTab === 'instance') {
        setSelectedRowKeys([]);
        setInstanceSelectedKeys([]);
      } else {
        setSelectedTreeKeys([]);
        setOrganizationSelectedKeys([]);
      }
    };

    const handleRemoveItem = (key: string) => {
      if (isInstance) {
        const newSelectedRowKeys = selectedRowKeys.filter(
          (item) => item !== key
        );
        setSelectedRowKeys(newSelectedRowKeys);
        setInstanceSelectedKeys(newSelectedRowKeys);
      } else {
        const newSelectedTreeKeys = selectedTreeKeys.filter(
          (item) => item !== key
        );
        setSelectedTreeKeys(newSelectedTreeKeys);
        setOrganizationSelectedKeys(newSelectedTreeKeys);
      }
    };

    const handleOrganizationSelect = (checkedKeys: any) => {
      const selectedKeys = checkedKeys.checked || checkedKeys;
      setSelectedTreeKeys(selectedKeys);
      setOrganizationSelectedKeys(selectedKeys);
    };

    const getInstanceName = (key: string) => {
      return selectedLabelMap[key] || key;
    };

    return (
      <div>
        <OperateModal
          title={title}
          visible={groupVisible}
          width="90vw"
          onClose={handleCancel}
          footer={
            <div>
              <Button
                className="mr-[10px]"
                type="primary"
                disabled={!selectedRowKeys.length && !selectedTreeKeys.length}
                onClick={handleSubmit}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <div>
            <Tabs activeKey={activeTab} items={tabs} onChange={changeTab} />
            <div className={selectInstanceStyle.selectInstance}>
              {isInstance ? (
                <div className={selectInstanceStyle.instanceList}>
                  <div className="flex items-center justify-between mb-[10px]">
                    <Input
                      className="w-[320px]"
                      allowClear
                      placeholder={t('common.searchPlaceHolder')}
                      value={searchText}
                      onClear={() => {
                        setSearchText('');
                        searchTextRef.current = '';
                        handleSearch();
                      }}
                      onChange={(e) => {
                        setSearchText(e.target.value);
                        searchTextRef.current = e.target.value;
                      }}
                      onPressEnter={handleSearch}
                    ></Input>
                  </div>
                  <CustomTable
                    rowSelection={rowSelection}
                    dataSource={tableData}
                    columns={columns}
                    pagination={pagination}
                    loading={tableLoading}
                    rowKey="instance_id"
                    scroll={{ x: 'max-content', y: 'calc(100vh - 370px)' }}
                    onChange={handleTableChange}
                  />
                </div>
              ) : (
                <div className={selectInstanceStyle.instanceList}>
                  <Input
                    value={treeSearchText}
                    className="w-[320px] mb-[10px]"
                    placeholder={t('common.searchPlaceHolder')}
                    onChange={(e) => setTreeSearchText(e.target.value)}
                  />
                  <Tree
                    checkable
                    checkStrictly
                    showLine
                    onCheck={handleOrganizationSelect}
                    checkedKeys={selectedTreeKeys}
                    treeData={filteredTreeData}
                    defaultExpandAll
                  />
                </div>
              )}
              <div className={selectInstanceStyle.previewList}>
                <div className="flex items-center justify-between mb-[10px]">
                  <span>
                    {t('common.selected')}（
                    <span className="text-[var(--color-primary)] px-[4px]">
                      {isInstance
                        ? selectedRowKeys.length
                        : selectedTreeKeys.length}
                    </span>
                    {t('common.items')}）
                  </span>
                  <span
                    className="text-[var(--color-primary)] cursor-pointer"
                    onClick={handleClearSelection}
                  >
                    {t('common.clear')}
                  </span>
                </div>
                <ul className={selectInstanceStyle.list}>
                  {isInstance
                    ? selectedRowKeys.map((key) => (
                      <li
                        className={selectInstanceStyle.listItem}
                        key={key}
                      >
                        <EllipsisWithTooltip
                          text={getInstanceName(key)}
                          className="w-[170px] overflow-hidden text-ellipsis whitespace-nowrap"
                        ></EllipsisWithTooltip>
                        <CloseOutlined
                          className={`text-[12px] ${selectInstanceStyle.operate}`}
                          onClick={() => handleRemoveItem(key)}
                        />
                      </li>
                    ))
                    : selectedTreeKeys.map((key) => (
                      <li className={selectInstanceStyle.listItem} key={key}>
                        <EllipsisWithTooltip
                          text={getLabelByKey(key, treeData)}
                          className="w-[170px] overflow-hidden text-ellipsis whitespace-nowrap"
                        ></EllipsisWithTooltip>
                        <CloseOutlined
                          className={`text-[12px] ${selectInstanceStyle.operate}`}
                          onClick={() => handleRemoveItem(key)}
                        />
                      </li>
                    ))}
                </ul>
              </div>
            </div>
          </div>
        </OperateModal>
      </div>
    );
  }
);

SelectAssets.displayName = 'selectAssets';
export default SelectAssets;
