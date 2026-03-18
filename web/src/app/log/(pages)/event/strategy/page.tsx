'use client';
import React, { useEffect, useState, useRef } from 'react';
import { Input, Button, message, Switch, Popconfirm } from 'antd';
import useApiClient from '@/utils/request';
import useLogEventApi from '@/app/log/api/event';
import { useAlgorithmList } from '@/app/log/hooks/event';
import assetStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import {
  ColumnItem,
  Pagination,
  TableDataItem,
  ListItem
} from '@/app/log/types';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { getRandomColor } from '@/app/log/utils/common';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { PlusOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import Permission from '@/components/permission';

const Strategy: React.FC = () => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getPolicy, patchPolicy, deletePolicy } = useLogEventApi();
  const ALGORITHM_LIST = useAlgorithmList();
  const { convertToLocalizedTime } = useLocalizedTime();
  const router = useRouter();
  const tableAbortControllerRef = useRef<AbortController | null>(null);
  const tableRequestIdRef = useRef<number>(0);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  });
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [searchText, setSearchText] = useState<string>('');
  const [enableLoading, setEnableLoading] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const columns: ColumnItem[] = [
    {
      title: t('common.name'),
      dataIndex: 'name',
      key: 'name'
    },
    {
      title: t('log.event.policyType'),
      dataIndex: 'alert_type',
      key: 'alert_type',
      render: (val) => (
        <>
          {ALGORITHM_LIST.find((item: ListItem) => item.value === val)?.title ||
            '--'}
        </>
      )
    },
    {
      title: t('common.creator'),
      dataIndex: 'created_by',
      key: 'created_by',
      render: (_, { created_by }) => {
        return created_by ? (
          <div className="column-user" title={created_by}>
            <span
              className="user-avatar"
              style={{ background: getRandomColor() }}
            >
              {created_by.slice(0, 1).toLocaleUpperCase()}
            </span>
            <span className="user-name">
              <EllipsisWithTooltip
                className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
                text={created_by}
              />
            </span>
          </div>
        ) : (
          <>--</>
        );
      }
    },
    {
      title: t('common.createTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      render: (_, { created_at }) => (
        <>{created_at ? convertToLocalizedTime(created_at) : '--'}</>
      )
    },
    {
      title: t('log.event.executionTime'),
      dataIndex: 'last_run_time',
      key: 'last_run_time',
      render: (_, { last_run_time }) => (
        <>{last_run_time ? convertToLocalizedTime(last_run_time) : '--'}</>
      )
    },
    {
      title: t('log.event.effective'),
      dataIndex: 'effective',
      key: 'effective',
      render: (_, record) => (
        <Permission
          requiredPermissions={['Edit']}
          instPermissions={record.permission}
        >
          <Switch
            size="small"
            loading={enableLoading}
            onChange={(val) => handleEffectiveChange(val, record.id)}
            checked={record.enable}
          />
        </Permission>
      )
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 120,
      render: (_, record) => (
        <>
          <Permission
            className="mr-[10px]"
            requiredPermissions={['Edit']}
            instPermissions={record.permission}
          >
            <Button
              type="link"
              onClick={() => linkToStrategyDetail('edit', record)}
            >
              {t('common.edit')}
            </Button>
          </Permission>
          <Permission
            requiredPermissions={['Delete']}
            instPermissions={record.permission}
          >
            <Popconfirm
              title={t('common.deleteTitle')}
              description={t('common.deleteContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              okButtonProps={{ loading: confirmLoading }}
              onConfirm={() => deleteConfirm(record.id)}
            >
              <Button type="link">{t('common.delete')}</Button>
            </Popconfirm>
          </Permission>
        </>
      )
    }
  ];

  useEffect(() => {
    if (isLoading) return;
    getAssetInsts();
  }, [isLoading, pagination.current, pagination.pageSize]);

  useEffect(() => {
    return () => {
      cancelAllRequests();
    };
  }, []);

  const cancelAllRequests = () => {
    tableAbortControllerRef.current?.abort();
  };

  const getParams = (text?: string) => {
    return {
      name: text ? '' : searchText,
      page: pagination.current,
      page_size: pagination.pageSize
    };
  };

  const handleEffectiveChange = async (val: boolean, id: number) => {
    try {
      setEnableLoading(true);
      await patchPolicy({
        enable: val,
        id
      });
      message.success(t(val ? 'common.started' : 'common.closed'));
      getAssetInsts();
    } finally {
      setEnableLoading(false);
    }
  };

  const handleTableChange = (pagination: any) => {
    setPagination(pagination);
  };

  const getAssetInsts = async (text?: string) => {
    tableAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    tableAbortControllerRef.current = abortController;
    const currentRequestId = ++tableRequestIdRef.current;
    try {
      setTableLoading(true);
      const params = getParams(text);
      const data = await getPolicy('', params, {
        signal: abortController.signal
      });
      if (currentRequestId !== tableRequestIdRef.current) return;
      setTableData(data.items || []);
      setPagination((pre) => ({
        ...pre,
        total: data.count
      }));
    } finally {
      if (currentRequestId === tableRequestIdRef.current) {
        setTableLoading(false);
      }
    }
  };

  const deleteConfirm = async (id: number | string) => {
    setConfirmLoading(true);
    try {
      await deletePolicy(id);
      message.success(t('common.successfullyDeleted'));
      getAssetInsts();
    } finally {
      setConfirmLoading(false);
    }
  };

  const enterText = () => {
    getAssetInsts();
  };

  const clearText = () => {
    setSearchText('');
    getAssetInsts('clear');
  };

  const linkToStrategyDetail = (type: string, row = { id: '', name: '' }) => {
    const params = new URLSearchParams({
      type,
      id: row.id,
      name: row.name
    });
    const targetUrl = `/log/event/strategy/detail?${params.toString()}`;
    router.push(targetUrl);
  };

  return (
    <div className={assetStyle.assetNoTree}>
      <div className={assetStyle.table}>
        <div className={assetStyle.search}>
          <div>
            <Input
              className="w-[320px]"
              placeholder={t('common.searchPlaceHolder')}
              allowClear
              onPressEnter={enterText}
              onClear={clearText}
              onChange={(e) => setSearchText(e.target.value)}
            ></Input>
          </div>
          <Permission requiredPermissions={['Add']}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => linkToStrategyDetail('add')}
            >
              {t('common.add')}
            </Button>
          </Permission>
        </div>
        <CustomTable
          scroll={{ y: 'calc(100vh - 336px)', x: 'calc(100vw - 500px)' }}
          columns={columns}
          dataSource={tableData}
          pagination={pagination}
          loading={tableLoading}
          rowKey="id"
          onChange={handleTableChange}
        ></CustomTable>
      </div>
    </div>
  );
};
export default Strategy;
