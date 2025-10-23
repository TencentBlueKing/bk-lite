'use client';

import React, { useEffect, useState, useRef } from 'react';
import OperateModal from './components/operateModal';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import Introduction from '@/app/alarm/components/introduction';
import { Tabs } from 'antd';
import { CorrelationRule } from '@/app/alarm/types/settings';
import { useSettingApi } from '@/app/alarm/api/settings';
import { Button, Input, Modal, message } from 'antd';
import { useTranslation } from '@/utils/i18n';

const CorrelationRulesPage: React.FC = () => {
  const { t } = useTranslation();
  const { getCorrelationRuleList, deleteCorrelationRule } = useSettingApi();
  const listCount = useRef<number>(0);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [operateVisible, setOperateVisible] = useState<boolean>(false);
  const [searchKey, setSearchKey] = useState<string>('');
  const [dataList, setDataList] = useState<CorrelationRule[]>([]);
  const [columns, setColumns] = useState<any[]>([]);
  const [currentRow, setCurrentRow] = useState<CorrelationRule | null>(null);
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [activeTab, setActiveTab] = useState<'Event' | 'Alert'>('Event');

  useEffect(() => {
    getTableList();
  }, []);

  const handleEdit = (type: 'add' | 'edit', row?: CorrelationRule) => {
    if (type === 'edit' && row) {
      setCurrentRow(row);
    } else {
      setCurrentRow(null);
    }
    setOperateVisible(true);
  };

  const handleDelete = async (row: CorrelationRule) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        try {
          await deleteCorrelationRule(row.id);
          message.success(t('successfullyDeleted'));
          if (pagination.current > 1 && listCount.current === 1) {
            setPagination((prev) => ({ ...prev, current: prev.current - 1 }));
            getTableList({
              current: pagination.current - 1,
              pageSize: pagination.pageSize,
            });
          } else {
            getTableList();
          }
        } catch {
          message.error(t('alarmCommon.operateFailed'));
        }
      },
    });
  };

  const getTableList = async (params: any = {}) => {
    try {
      setTableLoading(true);
      const searchVal =
        params.searchKey !== undefined ? params.searchKey : searchKey;
      const queryParams = {
        page: params.current || pagination.current,
        page_size: params.pageSize || pagination.pageSize,
        name: searchVal || undefined,
      };
      const data: any = await getCorrelationRuleList(queryParams);
      setDataList(data.items || []);
      listCount.current = data.items?.length || 0;
      setPagination((prev) => ({
        ...prev,
        total: data.count || 0,
      }));
    } catch {
      message.error('加载列表失败');
      return { data: [], total: 0, success: false };
    } finally {
      setTableLoading(false);
    }
  };

  const handleFilterChange = () => {
    setPagination({ ...pagination, current: 1 });
    getTableList({
      ...pagination,
      current: 1,
    });
  };

  const handleFilterClear = () => {
    setSearchKey('');
    setPagination((prev) => ({ ...prev, current: 1 }));
    getTableList({
      current: 1,
      pageSize: pagination.pageSize,
      searchKey: '',
    });
  };

  const handleTableChange = (newPagination: any) => {
    const curPage = newPagination;
    setPagination(curPage);
    getTableList({
      ...curPage,
    });
  };

  const buildColumns = () => {
    return [
      {
        title: t('settings.name'),
        dataIndex: 'name',
        key: 'name',
        width: 150,
      },
      {
        title: t('settings.correlation.type'),
        dataIndex: 'rule_names',
        key: 'rule_names',
        width: 150,
      },
      {
        title: t('settings.correlation.scope'),
        dataIndex: 'scope',
        key: 'scope',
        width: 150,
        render: (text: string) => {
          return text === 'all' ? t('alarmCommon.all') : '';
        },
      },
      {
        title: t('settings.correlation.windowType'),
        dataIndex: 'window_type',
        key: 'window_type',
        width: 150,
        render: (text: string) => {
          return text === 'sliding'
            ? t('settings.correlation.slidingWindow')
            : text === 'fixed'
              ? t('settings.correlation.fixedWindow')
              : text === 'session'
                ? t('settings.correlation.sessionWindow')
                : '';
        },
      },
      {
        title: t('settings.correlation.executionTime'),
        dataIndex: 'exec_time',
        key: 'exec_time',
        width: 150,
      },
      {
        title: t('settings.correlation.lastUpdateTime'),
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 150,
      },
      {
        title: t('settings.assignActions'),
        key: 'operation',
        width: 130,
        render: (text: any, row: CorrelationRule) => (
          <div className="flex gap-4">
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="link"
                size="small"
                onClick={() => handleEdit('edit', row)}
              >
                {t('common.edit')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Delete']}>
              <Button
                type="link"
                size="small"
                onClick={() => handleDelete(row)}
              >
                {t('common.delete')}
              </Button>
            </PermissionWrapper>
          </div>
        ),
      },
    ];
  };

  useEffect(() => {
    setColumns(buildColumns());
  }, [searchKey, pagination]);

  return (
    <>
      <Introduction
        title={t('settings.correlationRules')}
        message={t('settings.correlationRulesMessage')}
      />
      <div className="p-4 pt-0 bg-[var(--color-bg-1)] rounded-lg shadow">
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as 'Event' | 'Alert')}
          items={[
            { key: 'Event', label: t('alarms.event') },
            { key: 'Alert', label: t('alarms.alert') },
          ]}
        />
        {activeTab === 'Event' && (
          <div>
            <div className="nav-box flex justify-between mb-[14px]">
              <div className="flex items-center">
                <Input
                  allowClear
                  value={searchKey}
                  placeholder={t('common.search')}
                  style={{ width: 250 }}
                  onChange={(e) => setSearchKey(e.target.value)}
                  onPressEnter={handleFilterChange}
                  onClear={handleFilterClear}
                />
              </div>
              <PermissionWrapper requiredPermissions={['Add']}>
                <Button type="primary" onClick={() => handleEdit('add')}>
                  {t('common.addNew')}
                </Button>
              </PermissionWrapper>
            </div>
            <CustomTable
              size="middle"
              rowKey="id"
              loading={tableLoading}
              columns={columns}
              dataSource={dataList}
              pagination={pagination}
              onChange={handleTableChange}
              scroll={{ y: 'calc(100vh - 480px)' }}
            />
            <OperateModal
              open={operateVisible}
              onClose={() => setOperateVisible(false)}
              currentRow={currentRow}
              onSuccess={() => {
                setPagination((prev) => ({ ...prev, current: 1 }));
                getTableList({ current: 1, pageSize: pagination.pageSize });
              }}
            />
          </div>
        )}
        {activeTab === 'Alert' && (
          <div className="p-4 bg-[var(--color-bg-1)] rounded-lg shadow text-center">
            {t('settings.correlationAlertPlaceholder')}
          </div>
        )}
      </div>
    </>
  );
};

export default CorrelationRulesPage;
