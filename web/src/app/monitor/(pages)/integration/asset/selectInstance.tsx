'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useMemo,
} from 'react';
import { Button, Input } from 'antd';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useMonitorApi from '@/app/monitor/api';
import CustomTable from '@/components/custom-table';
import selectInstanceStyle from './selectInstance.module.scss';
import {
  ColumnItem,
  ModalRef,
  ModalConfig,
  Pagination,
  TableDataItem,
  ObjectItem,
} from '@/app/monitor/types';
import { getBaseInstanceColumn } from '@/app/monitor/utils/common';
import { CloseOutlined } from '@ant-design/icons';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

const SelectInstance = forwardRef<ModalRef, ModalConfig>(
  ({ onSuccess, monitorObject, list, objects }, ref) => {
    const { t } = useTranslation();
    const { getInstanceList } = useMonitorApi();
    const { convertToLocalizedTime } = useLocalizedTime();
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [pagination, setPagination] = useState<Pagination>({
      current: 1,
      total: 0,
      pageSize: 20,
    });
    const [title, setTitle] = useState<string>('');
    const [tableLoading, setTableLoading] = useState<boolean>(false);
    const [selectedRowKeys, setSelectedRowKeys] = useState<Array<any>>([]);
    const [tableData, setTableData] = useState<TableDataItem[]>([]);
    const [searchText, setSearchText] = useState<string>('');

    const columns = useMemo(() => {
      const columnItems: ColumnItem[] = [
        {
          title: t('common.time'),
          dataIndex: 'time',
          key: 'time',
          width: 160,
          render: (_, { time }) => (
            <>
              {time ? convertToLocalizedTime(new Date(time * 1000) + '') : '--'}
            </>
          ),
        },
      ];
      const row =
        objects.find((item: ObjectItem) => item.id === monitorObject) || {};
      return [
        ...getBaseInstanceColumn({
          objects: objects as ObjectItem[],
          row,
          t,
        }),
        ...columnItems,
      ];
    }, [objects, monitorObject, t]);

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
        setSelectedRowKeys((list as React.Key[]) || []);
        fetchData();
      },
    }));

    const onSelectChange = (selectedKeys: React.Key[]) => {
      setSelectedRowKeys(selectedKeys);
    };

    const rowSelection = {
      selectedRowKeys,
      onChange: onSelectChange,
    };

    const handleSubmit = async () => {
      handleCancel();
      onSuccess(selectedRowKeys);
    };

    const fetchData = async (type?: string) => {
      try {
        setTableLoading(true);
        const params = {
          page: pagination.current,
          page_size: pagination.pageSize,
          name: type === 'clear' ? '' : searchText,
        };
        const data = await getInstanceList(monitorObject as React.Key, params);
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
    };

    const handleTableChange = (pagination: any) => {
      setPagination(pagination);
    };

    const handleClearSelection = () => {
      setSelectedRowKeys([]); // 清空选中项
    };

    const handleRemoveItem = (key: string) => {
      const newSelectedRowKeys = selectedRowKeys.filter((item) => item !== key);
      setSelectedRowKeys(newSelectedRowKeys);
    };

    const clearText = () => {
      setSearchText('');
      fetchData('clear');
    };

    return (
      <div>
        <OperateModal
          title={title}
          visible={groupVisible}
          width={900}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                className="mr-[10px]"
                type="primary"
                disabled={!selectedRowKeys.length}
                onClick={handleSubmit}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <div className={selectInstanceStyle.selectInstance}>
            <div className={selectInstanceStyle.instanceList}>
              <div className="flex items-center justify-between mb-[10px]">
                <Input
                  allowClear
                  className="w-[320px]"
                  placeholder={t('common.searchPlaceHolder')}
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  onPressEnter={() => fetchData()}
                  onClear={clearText}
                ></Input>
              </div>
              <CustomTable
                rowSelection={rowSelection}
                dataSource={tableData}
                columns={columns}
                pagination={pagination}
                loading={tableLoading}
                rowKey="instance_id"
                scroll={{ x: 620, y: 'calc(100vh - 450px)' }}
                onChange={handleTableChange}
              />
            </div>
            <div className={selectInstanceStyle.previewList}>
              <div className="flex items-center justify-between mb-[10px]">
                <span>
                  {t('common.selected')}（
                  <span className="text-[var(--color-primary)] px-[4px]">
                    {selectedRowKeys.length}
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
                {selectedRowKeys.map((key) => {
                  const item = tableData.find(
                    (data) => data.instance_id === key
                  );
                  return (
                    <li className={selectInstanceStyle.listItem} key={key}>
                      <span>{item?.instance_name || '--'}</span>
                      <CloseOutlined
                        className={`text-[12px] ${selectInstanceStyle.operate}`}
                        onClick={() => handleRemoveItem(key)}
                      />
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        </OperateModal>
      </div>
    );
  }
);

SelectInstance.displayName = 'SelectInstance';
export default SelectInstance;
