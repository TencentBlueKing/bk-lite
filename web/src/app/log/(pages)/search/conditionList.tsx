'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from 'react';
import { Button, Popconfirm, message, Input } from 'antd';
import OperateModal from '@/app/log/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import {
  ModalRef,
  ModalConfig,
  TableDataItem,
  Pagination,
  TimeLineItem,
  ColumnItem,
} from '@/app/log/types';
import useLogApi from '@/app/log/api/search';
import CustomTable from '@/components/custom-table';
import Permission from '@/components/permission';

const { Search } = Input;

const ConditionList = forwardRef<ModalRef, ModalConfig>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { isLoading } = useApiClient();
    const { getLogCondition, delLogCondition } = useLogApi();
    const [visible, setVisible] = useState<boolean>(false);
    const [title, setTitle] = useState<string>('');
    const [pagination, setPagination] = useState<Pagination>({
      current: 1,
      total: 0,
      pageSize: 20,
    });
    const [tableLoading, setTableLoading] = useState<boolean>(false);
    const [tableData, setTableData] = useState<TimeLineItem[]>([]);
    const [confirmLoading, setConfirmLoading] = useState(false);
    const [searchText, setSearchText] = useState<string>('');

    const columns: ColumnItem[] = [
      {
        title: t('common.name'),
        dataIndex: 'name',
        key: 'name',
        width: 350,
      },
      {
        title: t('common.action'),
        key: 'action',
        dataIndex: 'action',
        width: 150,
        fixed: 'right',
        render: (_, record) => (
          <>
            <Button
              type="link"
              className="ml-[10px]"
              onClick={() => onConditonSearch(record)}
            >
              {t('log.search.query')}
            </Button>
            <Permission requiredPermissions={['Delete']}>
              <Popconfirm
                title={t('common.deleteTitle')}
                description={t('common.deleteContent')}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                okButtonProps={{ loading: confirmLoading }}
                onConfirm={() => deleteInstConfirm(record)}
              >
                <Button type="link" className="ml-[10px]">
                  {t('common.remove')}
                </Button>
              </Popconfirm>
            </Permission>
          </>
        ),
      },
    ];

    useImperativeHandle(ref, () => ({
      showModal: ({ title }) => {
        setVisible(true);
        setTitle(title);
        getTableData();
      },
    }));

    useEffect(() => {
      if (!isLoading) {
        getTableData();
      }
    }, [pagination.current, pagination.pageSize]);

    const getParams = () => {
      return {
        name: searchText,
        page: pagination.current,
        page_size: pagination.pageSize,
      };
    };

    const onConditonSearch = (row: TableDataItem) => {
      handleCancel();
      onSuccess(row.condition);
    };

    const handleSearch = (val: string) => {
      setSearchText(val);
      getTableData({
        ...getParams(),
        name: val,
      });
    };

    const deleteInstConfirm = async (row: TableDataItem) => {
      setConfirmLoading(true);
      try {
        await delLogCondition(row.id as number);
        message.success(t('common.successfullyDeleted'));
        if (pagination.current > 1 && tableData.length === 1) {
          setPagination((pre) => ({
            ...pre,
            current: pre.current--,
          }));
          return;
        }
        getTableData();
      } finally {
        setConfirmLoading(false);
      }
    };

    const getTableData = async (params = getParams()) => {
      setTableLoading(true);
      try {
        const data = await getLogCondition(params);
        setTableData(data?.items || []);
        setPagination((prev: Pagination) => ({
          ...prev,
          total: data?.count || 0,
        }));
      } finally {
        setTableLoading(false);
      }
    };

    const handleCancel = () => {
      setVisible(false);
      setSearchText('');
      setTableData([]);
    };

    const handleTableChange = (pagination: any) => {
      setPagination(pagination);
    };

    return (
      <div>
        <OperateModal
          title={title}
          visible={visible}
          width={600}
          destroyOnClose
          onClose={handleCancel}
          footer={
            <div>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <Search
            className="mb-[20px] w-[300px]"
            allowClear
            enterButton
            placeholder={t('common.searchPlaceHolder')}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={handleSearch}
          ></Search>
          <CustomTable
            scroll={{ y: 'calc(100vh - 316px)' }}
            columns={columns}
            dataSource={tableData}
            pagination={pagination}
            loading={tableLoading}
            rowKey="id"
            onChange={handleTableChange}
          ></CustomTable>
        </OperateModal>
      </div>
    );
  }
);

ConditionList.displayName = 'ConditionList';
export default ConditionList;
