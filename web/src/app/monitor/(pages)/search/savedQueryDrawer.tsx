'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect
} from 'react';
import { Button, Popconfirm, message, Input } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import useSearchApi from '@/app/monitor/api/search';
import CustomDrawer from '@/app/monitor/components/operate-drawer';
import {
  QueryGroup,
  QueryGroupData,
  SavedConditionItem,
  SavedQueryDrawerRef,
  SavedQueryDrawerProps
} from '@/app/monitor/types/search';
import CustomTable from '@/components/custom-table';

const transformToFrontendFormat = (groups: QueryGroupData[]): QueryGroup[] => {
  return groups.map((group) => ({
    id: crypto.randomUUID(),
    name: group.name,
    object: group.object,
    instanceIds: group.instance_ids,
    metric: group.metric,
    aggregation: group.aggregation,
    conditions: group.conditions,
    collapsed: false
  }));
};

const SavedQueryDrawer = forwardRef<SavedQueryDrawerRef, SavedQueryDrawerProps>(
  ({ onLoad }, ref) => {
    const { t } = useTranslation();
    const { isLoading } = useApiClient();
    const { convertToLocalizedTime } = useLocalizedTime();
    const { getMonitorConditions, deleteMonitorCondition } = useSearchApi();
    const [visible, setVisible] = useState<boolean>(false);
    const [tableData, setTableData] = useState<SavedConditionItem[]>([]);
    const [tableLoading, setTableLoading] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState(false);
    const [searchText, setSearchText] = useState<string>('');
    const [pagination, setPagination] = useState({
      current: 1,
      total: 0,
      pageSize: 20
    });

    const columns = [
      {
        title: t('common.name'),
        dataIndex: 'name',
        key: 'name',
        width: 200
      },
      {
        title: t('monitor.search.saveTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 200,
        render: (text: string) => (
          <>{text ? convertToLocalizedTime(text) : '--'}</>
        )
      },
      {
        title: t('common.action'),
        key: 'action',
        dataIndex: 'action',
        width: 120,
        render: (_: unknown, record: SavedConditionItem) => (
          <div className="flex gap-2">
            <Button type="link" size="small" onClick={() => handleLoad(record)}>
              {t('monitor.search.loadInto')}
            </Button>
            <Popconfirm
              title={t('common.deleteTitle')}
              description={t('common.deleteContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              okButtonProps={{ loading: confirmLoading }}
              onConfirm={() => handleDelete(record)}
            >
              <Button type="link" size="small" danger>
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </div>
        )
      }
    ];

    useImperativeHandle(ref, () => ({
      showDrawer: () => {
        setVisible(true);
        fetchData();
      }
    }));

    useEffect(() => {
      if (visible && !isLoading) {
        fetchData();
      }
    }, [pagination.current, pagination.pageSize]);

    const getParams = () => {
      return {
        name: searchText,
        page: pagination.current,
        page_size: pagination.pageSize
      };
    };

    const fetchData = async (params = getParams()) => {
      setTableLoading(true);
      try {
        const data = await getMonitorConditions(params);
        setTableData(data?.items || []);
        setPagination((prev) => ({
          ...prev,
          total: data?.count || 0
        }));
      } finally {
        setTableLoading(false);
      }
    };

    const handleSearch = (val: string) => {
      setSearchText(val);
      setPagination((prev) => ({ ...prev, current: 1 }));
      fetchData({
        ...getParams(),
        name: val,
        page: 1
      });
    };

    const handleLoad = (record: SavedConditionItem) => {
      if (record.condition) {
        const queryGroups = transformToFrontendFormat(record.condition);
        onLoad(queryGroups);
        handleClose();
      }
    };

    const handleDelete = async (record: SavedConditionItem) => {
      setConfirmLoading(true);
      try {
        await deleteMonitorCondition(record.id);
        message.success(t('common.successfullyDeleted'));
        if (pagination.current > 1 && tableData.length === 1) {
          setPagination((prev) => ({
            ...prev,
            current: prev.current - 1
          }));
          return;
        }
        fetchData();
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleClose = () => {
      setVisible(false);
      setSearchText('');
      setTableData([]);
    };

    const handleTableChange = (pag: {
      current: number;
      total: number;
      pageSize: number;
    }) => {
      setPagination(pag);
    };

    return (
      <CustomDrawer
        title={t('monitor.search.loadSavedQuery')}
        open={visible}
        width={600}
        destroyOnClose
        footer={
          <div>
            <Button onClick={handleClose}>{t('common.cancel')}</Button>
          </div>
        }
        onClose={handleClose}
      >
        <Input.Search
          className="mb-4 w-[300px]"
          allowClear
          enterButton={<SearchOutlined />}
          placeholder={t('monitor.search.searchByName')}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onSearch={handleSearch}
        />
        <CustomTable
          columns={columns}
          dataSource={tableData}
          pagination={pagination}
          loading={tableLoading}
          rowKey="id"
          onChange={handleTableChange}
          scroll={{ y: 'calc(100vh - 316px)' }}
        />
      </CustomDrawer>
    );
  }
);

SavedQueryDrawer.displayName = 'SavedQueryDrawer';
export default SavedQueryDrawer;
