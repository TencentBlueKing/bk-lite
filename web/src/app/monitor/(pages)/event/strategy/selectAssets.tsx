'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from 'react';
import { Button, Input, Tabs, Tree } from 'antd';
import OperateModal from '@/app/monitor/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import CustomTable from '@/components/custom-table';
import {
  ColumnItem,
  ModalRef,
  ModalConfig,
  TabItem,
  Pagination,
  TableDataItem,
} from '@/app/monitor/types';
import { CloseOutlined } from '@ant-design/icons';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import selectInstanceStyle from './selectInstance.module.scss';

const convertCascaderToTreeData = (cascaderData: any) => {
  return cascaderData.map((item: any) => {
    const { label, value, children } = item;
    return {
      title: label,
      key: value,
      children: children ? convertCascaderToTreeData(children) : [],
    };
  });
};

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

const getParentKeys = (
  key: string,
  treeData: any,
  parentKeys: string[] = []
) => {
  for (const node of treeData) {
    if (node.key === key) {
      return parentKeys;
    }
    if (node.children?.length) {
      const result: any = getParentKeys(key, node.children, [
        ...parentKeys,
        node.key,
      ]);
      if (result) return result;
    }
  }
  return null;
};

const SelectAssets = forwardRef<ModalRef, ModalConfig>(
  (
    { onSuccess, organizationList, monitorObject, form: { type, values } },
    ref
  ) => {
    const { t } = useTranslation();
    const { get } = useApiClient();
    const { convertToLocalizedTime } = useLocalizedTime();
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
    const columns: ColumnItem[] = [
      {
        title: t('common.name'),
        dataIndex: 'instance_name',
        key: 'instance_name',
        ellipsis: true,
      },
      {
        title: t('monitor.views.reportTime'),
        dataIndex: 'time',
        key: 'time',
        render: (_, { time }) => (
          <>
            {time ? convertToLocalizedTime(new Date(time * 1000) + '') : '--'}
          </>
        ),
      },
    ];

    useEffect(() => {
      fetchData();
    }, [pagination.current, pagination.pageSize]);

    useImperativeHandle(ref, () => ({
      showModal: ({ title }) => {
        // 开启弹窗的交互
        setPagination((prev: Pagination) => ({
          ...prev,
          current: 1,
        }));
        setTableData([]);
        setGroupVisible(true);
        setTitle(title);
        setActiveTab(type || 'instance');
        if (type === 'instance' || !type) {
          fetchData();
          setSelectedRowKeys(values);
        } else {
          setSelectedTreeKeys(values);
        }
      },
    }));

    const changeTab = (val: string) => {
      setActiveTab(val);
      setSelectedRowKeys([]);
      setSelectedTreeKeys([]);
      if (val === 'instance') {
        fetchData();
      }
    };

    const onSelectChange = (selectedKeys: any) => {
      setSelectedRowKeys(selectedKeys);
    };

    const rowSelection = {
      selectedRowKeys,
      onChange: onSelectChange,
    };

    const treeData = convertCascaderToTreeData(organizationList);
    const filteredTreeData = filterTreeData(treeData, treeSearchText);

    const handleSubmit = async () => {
      handleCancel();
      onSuccess({
        type: activeTab,
        values: activeTab === 'instance' ? selectedRowKeys : selectedTreeKeys,
      });
    };

    const fetchData = async (type?: string) => {
      try {
        setTableLoading(true);
        const data = await get(
          `/monitor/api/monitor_instance/${monitorObject}/list/`,
          {
            params: {
              page: pagination.current,
              page_size: pagination.pageSize,
              name: type === 'clear' ? '' : searchText,
            },
          }
        );
        setTableData(data?.results || []);
        setPagination((prev: Pagination) => ({
          ...prev,
          total: data?.count || 0,
        }));
      } finally {
        setTableLoading(false);
      }
    };

    const handleCancel = () => {
      setGroupVisible(false);
      setSelectedRowKeys([]); // 清空选中项
      setSelectedTreeKeys([]); // 清空选中项
      setSearchText('');
      setTreeSearchText('');
    };

    const handleTableChange = (pagination: any) => {
      setPagination(pagination);
    };

    const handleClearSelection = () => {
      setSelectedRowKeys([]); // 清空选中项
      setSelectedTreeKeys([]); // 清空选中项
    };

    const handleRemoveItem = (key: string) => {
      if (isInstance) {
        const newSelectedRowKeys = selectedRowKeys.filter(
          (item) => item !== key
        );
        setSelectedRowKeys(newSelectedRowKeys);
      } else {
        const parentKeys = getParentKeys(key, treeData) || [];
        const keysToRemove = [key, ...parentKeys];
        const newSelectedTreeKeys = selectedTreeKeys.filter(
          (item) => !keysToRemove.includes(item)
        );
        setSelectedTreeKeys(newSelectedTreeKeys);
      }
    };

    const handleOrganizationSelect = (selectedKeys: any) => {
      const newSelectedKeys = selectedKeys.filter((key: string) =>
        isLeafNode(key, filteredTreeData)
      );
      setSelectedTreeKeys(newSelectedKeys);
    };

    const clearText = () => {
      setSearchText('');
      fetchData('clear');
    };

    const isLeafNode = (key: string, treeData: any): boolean => {
      for (const node of treeData) {
        if (node.key === key) {
          return !node.children || node.children.length === 0;
        } else if (node.children) {
          const found = isLeafNode(key, node.children);
          if (found) return found;
        }
      }
      return false;
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
                      onPressEnter={() => fetchData()}
                      onClear={clearText}
                      onChange={(e) => setSearchText(e.target.value)}
                    ></Input>
                  </div>
                  <CustomTable
                    rowSelection={rowSelection}
                    dataSource={tableData}
                    columns={columns}
                    pagination={pagination}
                    loading={tableLoading}
                    rowKey="instance_id"
                    scroll={{ x: 520, y: 'calc(100vh - 370px)' }}
                    onChange={handleTableChange}
                  />
                </div>
              ) : (
                <div className="w-[550px]">
                  <Input
                    value={treeSearchText}
                    className="w-[320px] mb-[10px]"
                    placeholder={t('common.searchPlaceHolder')}
                    onChange={(e) => setTreeSearchText(e.target.value)}
                  />
                  <Tree
                    checkable
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
                        : selectedTreeKeys.filter((key) =>
                          isLeafNode(key, treeData)
                        ).length}
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
                      const item = tableData.find(
                        (data) => data.instance_id === key
                      );
                      return (
                        <li
                          className={selectInstanceStyle.listItem}
                          key={key}
                        >
                          <span>{item?.instance_name || '--'}</span>
                          <CloseOutlined
                            className={`text-[12px] ${selectInstanceStyle.operate}`}
                            onClick={() => handleRemoveItem(key)}
                          />
                        </li>
                      );
                    })
                    : selectedTreeKeys
                      .filter((key) => isLeafNode(key, treeData))
                      .map((key) => (
                        <li
                          className={selectInstanceStyle.listItem}
                          key={key}
                        >
                          <span>{getLabelByKey(key, treeData)}</span>
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
