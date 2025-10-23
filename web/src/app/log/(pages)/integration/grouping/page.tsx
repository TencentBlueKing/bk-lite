'use client';
import React, { useEffect, useState, useRef } from 'react';
import { Input, Button, message, Popconfirm, Spin } from 'antd';
import useApiClient from '@/utils/request';
import useLogApi from '@/app/log/api/integration';
import { useTranslation } from '@/utils/i18n';
import {
  ColumnItem,
  ModalRef,
  Organization,
  Pagination,
  TableDataItem,
} from '@/app/log/types';
import { ReloadOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import { useCommon } from '@/app/log/context/common';
import { showGroupName } from '@/app/log/utils/common';
import EditInstance from './editInstance';
import Permission from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { GroupInfo } from '@/app/log/types/integration';
const { Search } = Input;

const Grouping = () => {
  const { isLoading } = useApiClient();
  const { getLogStreams, deleteLogStream, getFields } = useLogApi();
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const commonContext = useCommon();
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const instanceRef = useRef<ModalRef>(null);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [searchText, setSearchText] = useState<string>('');
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [fields, setFields] = useState<string[]>([]);

  const columns: ColumnItem[] = [
    {
      title: t('common.name'),
      dataIndex: 'name',
      key: 'name',
      width: 160,
    },
    {
      title: t('log.integration.ruleDes'),
      dataIndex: 'rule',
      key: 'rule',
      width: 200,
      render: (_, { rule }) => (
        <EllipsisWithTooltip
          className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          text={getRuleDisplay(rule)}
        />
      ),
    },
    {
      title: t('common.belongingGroup'),
      dataIndex: 'organizations',
      key: 'organizations',
      width: 160,
      render: (_, { organizations }) => (
        <EllipsisWithTooltip
          className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          text={showGroupName(organizations, organizationList)}
        />
      ),
    },
    {
      title: t('common.createTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (val: any) => {
        return <>{convertToLocalizedTime(val, 'YYYY-MM-DD HH:mm:ss')}</>;
      },
    },
    {
      title: t('common.creator'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 160,
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <>
          <Permission requiredPermissions={['Edit']}>
            <Button
              type="link"
              className="ml-[10px]"
              onClick={() => openInstanceModal(record, 'edit')}
            >
              {t('common.edit')}
            </Button>
          </Permission>
          <Permission requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('common.deleteTitle')}
              description={t('common.deleteContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              okButtonProps={{ loading: confirmLoading }}
              onConfirm={() => deleteInstConfirm(record)}
            >
              <Button
                type="link"
                className="ml-[10px]"
                disabled={record.id === 'default'}
              >
                {t('common.remove')}
              </Button>
            </Popconfirm>
          </Permission>
        </>
      ),
    },
  ];

  useEffect(() => {
    if (!isLoading) {
      getLogGroups(searchText);
    }
  }, [pagination.current, pagination.pageSize]);

  useEffect(() => {
    if (!isLoading) {
      initPage();
    }
  }, [isLoading]);

  const initPage = () => {
    setPageLoading(true);
    Promise.all([
      getCollectTypeList(),
      getLogGroups(searchText, 'init'),
    ]).finally(() => {
      setPageLoading(false);
    });
  };

  const getRuleDisplay = (rule: GroupInfo) => {
    const { mode, conditions = [] } = rule || {};
    if (!mode) {
      return '*';
    }
    if (mode === 'OR') {
      return `${t('log.integration.anySatisfy')}${conditions.length}${t(
        'log.integration.anyOneof'
      )}`;
    }
    return `${t('log.integration.allSatisfy')}${conditions.length}${t(
      'log.integration.allRules'
    )}`;
  };

  const getCollectTypeList = async (params = {}) => {
    const data = await getFields(params);
    setFields(data);
  };

  const openInstanceModal = (row: TableDataItem, type: string) => {
    instanceRef.current?.showModal({
      title: t(`common.${type}`),
      type: row.id === 'default' ? 'builtIn' : type,
      form: row,
    });
  };

  const handleTableChange = (pagination: any) => {
    setPagination(pagination);
  };

  const getLogGroups = async (val: string, type?: string) => {
    try {
      setTableLoading(type !== 'init');
      const params = {
        page: pagination.current,
        page_size: pagination.pageSize,
        name: val || '',
      };
      const data = await getLogStreams(params);
      setTableData(data?.items || []);
      setPagination((prev: Pagination) => ({
        ...prev,
        total: data?.count || 0,
      }));
    } finally {
      setTableLoading(false);
    }
  };

  const deleteInstConfirm = async (row: TableDataItem) => {
    setConfirmLoading(true);
    try {
      await deleteLogStream(row.id as number);
      message.success(t('common.successfullyDeleted'));
      onRefresh();
    } finally {
      setConfirmLoading(false);
    }
  };

  const onRefresh = () => {
    getLogGroups(searchText);
  };

  const handleSearch = (val: string) => {
    setSearchText(val);
    getLogGroups(val);
  };

  return (
    <div className="bg-[var(--color-bg-1)] h-full p-[20px]">
      <Spin spinning={pageLoading}>
        <div className="flex justify-end items-center mb-[10px]">
          <Search
            allowClear
            enterButton
            className="mr-[8px] w-60"
            placeholder={t('common.searchPlaceHolder')}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={handleSearch}
          ></Search>
          <Permission requiredPermissions={['Add']}>
            <Button
              className="mr-[8px]"
              type="primary"
              onClick={() => openInstanceModal({}, 'add')}
            >
              + {t('common.add')}
            </Button>
          </Permission>
          <Button icon={<ReloadOutlined />} onClick={onRefresh} />
        </div>
        <CustomTable
          scroll={{ y: 'calc(100vh - 320px)', x: 'calc(100vh - 80px)' }}
          columns={columns}
          dataSource={tableData}
          pagination={pagination}
          loading={tableLoading}
          rowKey="id"
          onChange={handleTableChange}
        ></CustomTable>
      </Spin>
      <EditInstance ref={instanceRef} fields={fields} onSuccess={onRefresh} />
    </div>
  );
};

export default Grouping;
