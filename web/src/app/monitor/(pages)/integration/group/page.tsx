'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Input, Button, Popconfirm, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import { useTranslation } from '@/utils/i18n';
import {
  ColumnItem,
  TreeItem,
  ModalRef,
  Organization,
  Pagination,
  ObjectItem,
  TableDataItem,
} from '@/app/monitor/types';
import { RuleInfo } from '@/app/monitor/types/integration';
import CustomTable from '@/components/custom-table';
import RuleModal from './ruleModal';
import { useCommon } from '@/app/monitor/context/common';
import TreeSelector from '@/app/monitor/components/treeSelector';
import DeleteRule from './deleteRuleModal';
import { showGroupName } from '@/app/monitor/utils/common';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import Permission from '@/components/permission';
import { cloneDeep } from 'lodash';

const GroupPage = () => {
  const { isLoading } = useApiClient();
  const { getMonitorObject } = useMonitorApi();
  const { getInstanceGroupRule } = useIntegrationApi();
  const { t } = useTranslation();
  const commonContext = useCommon();
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const ruleRef = useRef<ModalRef>(null);
  const deleteModalRef = useRef<ModalRef>(null);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [ruleLoading, setRuleLoading] = useState<boolean>(false);
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [ruleList, setRuleList] = useState<RuleInfo[]>([]);
  const [searchText, setSearchText] = useState<string>('');
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [objectId, setObjectId] = useState<React.Key>('');

  const columns = useMemo(() => {
    const columnItems: ColumnItem[] = [
      {
        title: t('monitor.integrations.ruleName'),
        dataIndex: 'name',
        key: 'name',
        width: 200,
      },
      {
        title: t('monitor.integrations.objectType'),
        dataIndex: 'monitor_object',
        key: 'monitor_object',
        width: 150,
        render: (_, { monitor_object }) => (
          <Tag color="blue">{getObjectTypeName(monitor_object)}</Tag>
        ),
      },
      {
        title: t('monitor.integrations.ruleDescription'),
        dataIndex: 'rule',
        key: 'rule',
        width: 200,
        render: (_, record: any) => {
          const count = record.rule?.filter?.length || 0;
          return (
            <>
              {t('monitor.integrations.exactMatch')}
              {count}
              {t('monitor.integrations.rulesCount')}
            </>
          );
        },
      },
      {
        title: t('monitor.group'),
        dataIndex: 'organizations',
        key: 'organizations',
        width: 200,
        render: (_, { organizations }) => (
          <EllipsisWithTooltip
            className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
            text={showGroupName(organizations, organizationList)}
          />
        ),
      },
      {
        title: t('common.action'),
        key: 'action',
        dataIndex: 'action',
        width: 150,
        fixed: 'right',
        render: (_, record: TableDataItem) => (
          <Space>
            <Permission
              requiredPermissions={['Edit']}
              instPermissions={record.permission}
            >
              <Button type="link" onClick={() => openRuleModal('edit', record)}>
                {t('common.edit')}
              </Button>
            </Permission>
            <Permission
              requiredPermissions={['Delete']}
              instPermissions={record.permission}
            >
              <Popconfirm
                title={t('common.deleteTitle')}
                description={t('monitor.integrations.deleteRuleTips')}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                onConfirm={() => showDeleteConfirm(record as RuleInfo)}
              >
                <Button type="link">{t('common.delete')}</Button>
              </Popconfirm>
            </Permission>
          </Space>
        ),
      },
    ];
    return columnItems;
  }, [objects, objectId, t, organizationList]);

  useEffect(() => {
    if (!isLoading) {
      getObjects();
    }
  }, [isLoading]);

  useEffect(() => {
    if (objectId) {
      getRuleList(objectId);
    }
  }, [objectId, pagination.current, pagination.pageSize]);

  const handleObjectChange = (id: string) => {
    setRuleList([]);
    setObjectId(id);
    setPagination((prev) => ({
      ...prev,
      current: 1,
    }));
  };

  const openRuleModal = (type: string, row = {}) => {
    const title: string = t(
      type === 'add'
        ? 'monitor.integrations.addRule'
        : 'monitor.integrations.editRule'
    );
    ruleRef.current?.showModal({
      title,
      type,
      form: row,
    });
  };

  const handleTableChange = (pagination: any) => {
    setPagination(pagination);
  };

  const getRuleList = async (objectId: React.Key, type?: string) => {
    try {
      setRuleLoading(type !== 'timer');
      const params: any = {
        monitor_object_id: objectId === 'all' ? '' : objectId,
        page: pagination.current,
        page_size: pagination.pageSize,
        name: type === 'clear' ? '' : searchText,
      };
      const data = await getInstanceGroupRule(params);
      setRuleList(data?.items || []);
      setPagination((prev: Pagination) => ({
        ...prev,
        total: data?.count || 0,
      }));
    } finally {
      setRuleLoading(false);
    }
  };

  const getObjects = async (type?: string) => {
    try {
      setTreeLoading(type !== 'timer');
      const params = {
        name: '',
      };
      const data = await getMonitorObject(params);
      setObjects(data);
      const _treeData = getTreeData(cloneDeep(data));
      setTreeData(_treeData);
    } finally {
      setTreeLoading(false);
    }
  };

  const getTreeData = (data: ObjectItem[]): TreeItem[] => {
    const groupedData = data.reduce((acc, item) => {
      if (!acc[item.type]) {
        acc[item.type] = {
          title: item.display_type || '--',
          key: item.type,
          children: [],
        };
      }
      acc[item.type].children.push({
        title: item.display_name || '--',
        key: item.id,
        children: [],
      });
      return acc;
    }, {} as Record<string, TreeItem>);
    return [
      {
        title: t('common.all'),
        key: 'all',
        children: [],
      },
      ...Object.values(groupedData),
    ];
  };

  const operateRule = () => {
    getRuleList(objectId);
  };

  const getObjectTypeName = (monitorObjectId: number) => {
    const obj = objects.find((item) => item.id === monitorObjectId);
    if (!obj) return '--';
    return `${obj.display_type || '--'}/${obj.display_name || '--'}`;
  };

  const showDeleteConfirm = (row: RuleInfo) => {
    deleteModalRef.current?.showModal({
      title: t('common.prompt'),
      form: row as Record<string, unknown>,
      type: 'delete',
    });
  };

  const clearText = () => {
    setSearchText('');
    getRuleList(objectId, 'clear');
  };

  return (
    <div className="flex overflow-hidden">
      <div className="w-[210px] min-w-[210px] flex flex-col h-[calc(100vh-146px)] overflow-y-auto overflow-x-hidden p-[20px_10px] bg-[var(--color-bg-1)]">
        <TreeSelector
          showAllMenu
          data={treeData}
          defaultSelectedKey={'all'}
          onNodeSelect={handleObjectChange}
          loading={treeLoading}
        />
      </div>
      <div className="w-[calc(100vw-250px)] bg-[var(--color-bg-1)] h-[calc(100vh-146px)] p-[20px] ml-[10px]">
        <div className="flex items-center justify-between mb-[10px]">
          <Input
            allowClear
            className="w-[320px]"
            placeholder={t('monitor.integrations.searchRuleName')}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onPressEnter={operateRule}
            onClear={clearText}
          />
          <Permission requiredPermissions={['Add']}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => openRuleModal('add')}
              disabled={objectId === 'all'}
            >
              {t('common.add')}
            </Button>
          </Permission>
        </div>
        <CustomTable
          scroll={{ y: 'calc(100vh - 330px)' }}
          columns={columns}
          dataSource={ruleList}
          pagination={pagination}
          loading={ruleLoading}
          rowKey="id"
          onChange={handleTableChange}
        />
      </div>
      <RuleModal
        ref={ruleRef}
        monitorObject={objectId}
        groupList={organizationList}
        objects={objects}
        onSuccess={operateRule}
      />
      <DeleteRule ref={deleteModalRef} onSuccess={operateRule} />
    </div>
  );
};

export default GroupPage;
