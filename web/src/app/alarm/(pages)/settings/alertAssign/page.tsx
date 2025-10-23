'use client';

import React, { useState, useEffect, useRef } from 'react';
import dayjs from 'dayjs';
import OperateModal from './components/operateModal';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import UserAvatar from '@/components/user-avatar';
import Introduction from '@/app/alarm/components/introduction';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { AlertAssignListItem } from '@/app/alarm/types/settings';
import { useSettingApi } from '@/app/alarm/api/settings';
import { Button, Input, Modal, message, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { typeLabel, weekMap } from '@/app/alarm/constants/settings';

const AlertAssign: React.FC = () => {
  const { t } = useTranslation();
  const { getAssignmentList, deleteAssignment, patchAssignment } =
    useSettingApi();
  const listCount = useRef<number>(0);
  const { convertToLocalizedTime } = useLocalizedTime();
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [loadingIds, setLoadingIds] = useState<Record<number, boolean>>({});
  const [operateVisible, setOperateVisible] = useState<boolean>(false);
  const [searchKey, setSearchKey] = useState<string>('');
  const [dataList, setDataList] = useState<AlertAssignListItem[]>([]);
  const [columns, setColumns] = useState<any[]>([]);
  const [currentRow, setCurrentRow] = useState<AlertAssignListItem | null>(
    null
  );
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  useEffect(() => {
    getTableList();
  }, []);

  const handleEdit = (type: 'add' | 'edit', row?: AlertAssignListItem) => {
    if (type === 'edit' && row) {
      setCurrentRow(row);
    } else {
      setCurrentRow(null);
    }
    setOperateVisible(true);
  };

  const handleDelete = async (row: AlertAssignListItem) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        try {
          await deleteAssignment(row.id);
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
          message.error(t('AlertAssign.operateFailed'));
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
      const data: any = await getAssignmentList(queryParams);
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

  const handleStatusToggle = async (
    row: AlertAssignListItem,
    checked: boolean
  ) => {
    setLoadingIds((ids) => ({ ...ids, [row.id]: true }));
    try {
      const data = await patchAssignment(row.id, { is_active: checked });
      if (!data) {
        message.error(t('alarmCommon.operateFailed'));
      } else {
        message.success(
          checked ? t('settings.enableSuccess') : t('settings.disableSuccess')
        );
      }
      getTableList();
    } catch {
      console.error(t('alarmCommon.operateFailed'));
    } finally {
      setLoadingIds((ids) => {
        const nxt = { ...ids };
        delete nxt[row.id];
        return nxt;
      });
    }
  };

  const buildColumns = () => {
    return [
      {
        title: t('settings.assignName'),
        dataIndex: 'name',
        key: 'name',
        width: 150,
      },
      {
        title: t('settings.assignPersonnel'),
        dataIndex: 'personnel',
        key: 'personnel',
        width: 180,
        shouldCellUpdate: (
          prev: AlertAssignListItem,
          next: AlertAssignListItem
        ) => prev?.personnel?.join(',') !== next?.personnel?.join(','),
        render: (_: any, { personnel }: AlertAssignListItem) =>
          personnel ? <UserAvatar userName={personnel.join(',')} /> : '--',
      },
      {
        title: t('settings.assignTime'),
        key: 'assignTime',
        width: 220,
        render: (_: any, row: AlertAssignListItem) => {
          const { type, start_time, end_time, week_month } = row.config as any;
          let label = typeLabel[type] || '';

          const fmt = (t: any, pattern = 'HH:mm:ss') =>
            dayjs(t, pattern).format(pattern);

          if (type === 'one') {
            return `${fmt(start_time, 'YYYY-MM-DD HH:mm:ss')}-${fmt(end_time, 'YYYY-MM-DD HH:mm:ss')}`;
          } else if (type === 'week') {
            label += ` ${(week_month || []).map((d: number) => weekMap[d]).join(',')}`;
          } else if (type === 'month') {
            label += ` ${(week_month || []).map((d: number) => `${d}日`).join(',')}`;
          }
          return `${label} ${fmt(start_time)} - ${fmt(end_time)}`;
        },
      },
      {
        title: t('settings.assignStatus'),
        dataIndex: 'assignStatus',
        key: 'assignStatus',
        width: 100,
        render: (_: any, row: AlertAssignListItem) => {
          const { is_active } = row;
          return is_active ? (
            <span style={{ color: '#00ba6c' }}>{t('settings.effective')}</span>
          ) : (
            <span style={{ color: '#CE241B' }}>
              {t('settings.ineffective')}
            </span>
          );
        },
      },
      {
        title: t('settings.assignCreateTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 180,
        render: (val: string) => {
          return convertToLocalizedTime(val, 'YYYY-MM-DD HH:mm:ss');
        },
      },
      {
        title: t('settings.assignStartStop'),
        dataIndex: 'is_active',
        key: 'is_active',
        width: 110,
        render: (val: boolean, row: AlertAssignListItem) => (
          <Switch
            loading={!!loadingIds[row.id]}
            checked={val}
            onChange={(checked) => handleStatusToggle(row, checked)}
          />
        ),
      },
      {
        title: t('settings.assignActions'),
        key: 'operation',
        width: 130,
        render: (text: any, row: AlertAssignListItem) => (
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
  }, [loadingIds, searchKey, pagination]);

  return (
    <>
      <Introduction
        title={t('settings.alertAssign')}
        message={t('settings.assignStrategyMessage')}
      />
      <div className="oid-library-container p-4 bg-[var(--color-bg-1)] rounded-lg shadow">
        <div className="nav-box flex justify-between mb-[20px]">
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
          scroll={{ y: 'calc(100vh - 440px)' }}
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
    </>
  );
};

export default AlertAssign;
