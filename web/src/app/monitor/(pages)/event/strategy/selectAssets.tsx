'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useMemo,
} from 'react';
import { Button, Input, Tabs, Tree } from 'antd';
import OperateModal from '@/app/monitor/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import useMonitorApi from '@/app/monitor/api';
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
} from '@/app/monitor/types';
import { CloseOutlined } from '@ant-design/icons';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import selectInstanceStyle from './selectInstance.module.scss';
import {
  getBaseInstanceColumn,
  showInstName,
} from '@/app/monitor/utils/common';
import { useUserInfoContext } from '@/context/userInfo';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

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

const getLabelByKey = (key: string, treeData: any): string => {
  for (const node of treeData) {
    if (node.key === key) {
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
    const { getInstanceList } = useMonitorApi();
    const { convertToLocalizedTime } = useLocalizedTime();
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
    const [allTableData, setAllTableData] = useState<TableDataItem[]>([]);
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

    const columns = useMemo(() => {
      const columnItems: ColumnItem[] = [
        {
          title: t('monitor.views.reportTime'),
          dataIndex: 'time',
          width: 160,
          key: 'time',
          render: (_, { time }) => (
            <>
              {time ? convertToLocalizedTime(new Date(time * 1000) + '') : '--'}
            </>
          ),
        },
      ];
      const row =
        (objects as ObjectItem[])?.find(
          (item: ObjectItem) => item.id === Number(monitorObject as React.Key)
        ) || ({} as ObjectItem);
      return [
        ...getBaseInstanceColumn({
          objects: objects as ObjectItem[],
          row,
          t,
        }),
        ...columnItems,
      ];
    }, [objects, monitorObject, t]);

    const treeData = useMemo(() => {
      return convertGroupTreeToTreeSelectData(groupTree);
    }, [groupTree]);

    const filteredTreeData = useMemo(() => {
      return filterTreeData(treeData, treeSearchText);
    }, [treeData, treeSearchText]);

    // 处理表格数据：前端搜索和分页
    const { tableData, paginationInfo } = useMemo(() => {
      let filteredData = allTableData;
      if (searchText) {
        filteredData = allTableData.filter((item) =>
          item.instance_name?.toLowerCase().includes(searchText.toLowerCase())
        );
      }
      const total = filteredData.length;
      const startIndex = (pagination.current - 1) * pagination.pageSize;
      const endIndex = startIndex + pagination.pageSize;
      const paginatedData = filteredData.slice(startIndex, endIndex);
      return {
        tableData: paginatedData,
        paginationInfo: {
          ...pagination,
          total: total,
        },
      };
    }, [allTableData, searchText, pagination.current, pagination.pageSize]);

    // 更新分页信息
    useEffect(() => {
      if (paginationInfo.total !== pagination.total) {
        setPagination(paginationInfo);
      }
    }, [paginationInfo, pagination.total]);

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form: { type, values, id } }) => {
        // 开启弹窗的交互
        setPagination((prev: Pagination) => ({
          ...prev,
          current: 1,
        }));
        setAllTableData([]);
        setGroupVisible(true);
        setTitle(title);
        setRowId(id as number);
        setActiveTab((type as string) || 'instance');
        if (type === 'instance' || !type) {
          fetchData();
          setInstanceSelectedKeys((values as string[]) || []);
          setSelectedRowKeys((values as string[]) || []);
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
        if (!allTableData.length) {
          fetchData();
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
    };

    const rowSelection = {
      selectedRowKeys: selectedRowKeys.filter((key) =>
        tableData.some((item) => item.instance_id === key)
      ),
      onChange: onSelectChange,
    };

    const handleSubmit = async () => {
      handleCancel();
      onSuccess(
        {
          type: activeTab,
          values: activeTab === 'instance' ? selectedRowKeys : selectedTreeKeys,
        },
        rowId
      );
    };

    const fetchData = async () => {
      try {
        setTableLoading(true);
        const data = await getInstanceList(monitorObject as React.Key, {
          page: 1,
          page_size: -1,
          name: '',
        });
        const results = data?.results || [];
        setAllTableData(results);
      } finally {
        setTableLoading(false);
      }
    };

    const handleCancel = () => {
      setGroupVisible(false);
      setSelectedRowKeys([]);
      setSelectedTreeKeys([]);
      setInstanceSelectedKeys([]);
      setOrganizationSelectedKeys([]);
      setSearchText('');
      setTreeSearchText('');
    };

    const handleTableChange = (pagination: any) => {
      setPagination(pagination);
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

    const clearText = () => {
      setSearchText('');
    };

    const getInstanceName = (row: TableDataItem) => {
      const objectItem =
        (objects as ObjectItem[])?.find(
          (item: ObjectItem) => item.id === Number(monitorObject as React.Key)
        ) || ({} as ObjectItem);
      return showInstName(objectItem, row);
    };

    return (
      <div>
        <OperateModal
          title={title}
          visible={groupVisible}
          width={800}
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
                      onClear={clearText}
                      onChange={(e) => {
                        setSearchText(e.target.value);
                        setPagination((prev) => ({
                          ...prev,
                          current: 1,
                        }));
                      }}
                    ></Input>
                  </div>
                  <CustomTable
                    rowSelection={rowSelection}
                    dataSource={tableData}
                    columns={columns}
                    pagination={paginationInfo}
                    loading={tableLoading}
                    rowKey="instance_id"
                    scroll={{ x: 520, y: 'calc(100vh - 370px)' }}
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
                    ? selectedRowKeys.map((key) => {
                      const item = allTableData.find(
                        (data) => data.instance_id === key
                      );
                      return (
                        <li
                          className={selectInstanceStyle.listItem}
                          key={key}
                        >
                          <EllipsisWithTooltip
                            text={getInstanceName(item as TableDataItem)}
                            className="w-[170px] overflow-hidden text-ellipsis whitespace-nowrap"
                          ></EllipsisWithTooltip>
                          <CloseOutlined
                            className={`text-[12px] ${selectInstanceStyle.operate}`}
                            onClick={() => handleRemoveItem(key)}
                          />
                        </li>
                      );
                    })
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
