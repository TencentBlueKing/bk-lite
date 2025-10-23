'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import dayjs from 'dayjs';
import styles from './index.module.scss';
import K8sTask from './components/k8sTask';
import VMTask from './components/vmTask';
import SNMPTask from './components/snmpTask';
import SQLTask from './components/sqlTask';
import CloudTask from './components/cloudTask';
import HostTask from './components/hostTask';
import TaskDetail from './components/taskDetail';
import { useCollectApi } from '@/app/cmdb/api';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import type { TableColumnType } from 'antd';
import type { ColumnItem } from '@/app/cmdb/types/assetManage';
import type { ColumnType } from 'antd/es/table';
import { Modal } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { Input, Button, Spin, Tag, Tree, Drawer, message, Tabs } from 'antd';
import {
  createExecStatusMap,
  ExecStatusKey,
  ExecStatus,
  getExecStatusConfig,
  EXEC_STATUS,
  ExecStatusType,
} from '@/app/cmdb/constants/professCollection';
import {
  CollectTask,
  TreeNode,
  CollectTaskMessage,
  ModelItem,
} from '@/app/cmdb/types/autoDiscovery';

type ExtendedColumnItem = ColumnType<CollectTask> & {
  key: string;
  dataIndex?: string;
};

const ProfessionalCollection: React.FC = () => {
  const { t } = useTranslation();
  const collectApi = useCollectApi();
  const ExecStatusMap = React.useMemo(() => createExecStatusMap(t), [t]);
  const execStatusConfig = React.useMemo(() => getExecStatusConfig(t), [t]);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [treeData, setTreeData] = useState<TreeNode[]>([]);
  const [detailVisible, setDetailVisible] = useState(false);
  const [currentTask, setCurrentTask] = useState<CollectTask | null>(null);
  const [activeTab, setActiveTab] = useState<string>('');
  const [tableData, setTableData] = useState<CollectTask[]>([]);
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);
  const [displayFieldKeys, setDisplayFieldKeys] = useState<string[]>([]);
  const [allColumns, setAllColumns] = useState<ExtendedColumnItem[]>([]);
  const [currentColumns, setCurrentColumns] = useState<ExtendedColumnItem[]>(
    []
  );
  const [treeLoading, setTreeLoading] = useState(false);
  const [tableLoading, setTableLoading] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [executingTaskIds, setExecutingTaskIds] = useState<number[]>([]);
  const tableCountRef = useRef<number>(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const stateRef = useRef({
    searchText: '',
    pagination: {
      current: 1,
      pageSize: 20,
      total: 0,
    },
    currentExecStatus: undefined as ExecStatusType | undefined,
    activeTab: '',
  });
  const selectedRef = useRef<{
    nodeId: string;
    node?: TreeNode;
  }>({ nodeId: '' });
  const [searchTextUI, setSearchTextUI] = useState('');
  const [paginationUI, setPaginationUI] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });

  const getAllKeys = (nodes: TreeNode[]): string[] => {
    let keys: string[] = [];
    nodes.forEach((node) => {
      keys.push(node.id);
      if (node.children) {
        keys = keys.concat(getAllKeys(node.children));
      }
    });
    return keys;
  };

  const getParams = (tabId?: string) => {
    const modelId = tabId || stateRef.current.activeTab;

    return {
      page: stateRef.current.pagination.current,
      page_size: stateRef.current.pagination.pageSize,
      model_id: modelId,
      name: stateRef.current.searchText,
      ...(stateRef.current.currentExecStatus !== undefined && {
        exec_status: stateRef.current.currentExecStatus,
      }),
    };
  };

  const fetchData = async (showLoading = true, tabId?: string) => {
    try {
      if (!selectedRef.current.nodeId) return;
      if (showLoading) {
        setTableLoading(true);
      }
      const params = getParams(tabId);
      const data = await collectApi.getCollectList(params);
      setTableData(data.items || []);
      tableCountRef.current = data.items.length || 0;
      setPaginationUI((prev) => ({
        ...prev,
        total: data.count || 0,
      }));
    } catch (error) {
      console.error('Failed to fetch table data:', error);
    } finally {
      if (showLoading) {
        setTableLoading(false);
      }
      resetTimer(tabId);
    }
  };

  const resetTimer = (tabId?: string) => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    const currentTabId = tabId || stateRef.current.activeTab;
    timerRef.current = setTimeout(
      () => fetchData(false, currentTabId),
      10 * 1000
    );
  };

  useEffect(() => {
    fetchData();
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [selectedRef.current.nodeId]);

  const fetchTreeData = async () => {
    try {
      setTreeLoading(true);
      const data = await collectApi.getCollectModelTree();
      const treeData = data.map((node: TreeNode) => {
        getItems(node);
        return node;
      });
      setTreeData(treeData);
      setExpandedKeys(getAllKeys(data));
      if (!data.length) return;

      const firstItem = data[0];
      const defaultKey = firstItem.children?.length
        ? firstItem.children[0].id
        : firstItem.id;

      selectedRef.current = {
        nodeId: defaultKey,
        node: treeData.find((node: TreeNode) => node.id === defaultKey),
      };

      setActiveTab(firstItem.tabItems?.[0]?.id || '');
      stateRef.current.activeTab = firstItem.tabItems?.[0]?.id || '';
    } catch (error) {
      console.error('Failed to fetch tree data:', error);
    } finally {
      setTreeLoading(false);
    }
  };

  useEffect(() => {
    fetchTreeData();
  }, []);

  const handleEnterSearch = () => {
    stateRef.current.pagination.current = 1;
    setPaginationUI((prev) => ({ ...prev, current: 1 }));
    stateRef.current.searchText = searchTextUI;
    fetchData();
  };

  const handleClearSearch = () => {
    setSearchTextUI('');
    stateRef.current.searchText = '';
    stateRef.current.pagination.current = 1;
    setPaginationUI((prev) => ({ ...prev, current: 1 }));
    fetchData();
  };

  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setSearchTextUI(e.target.value);
    },
    []
  );

  const handleTableChange = (pagination: any, filters: any) => {
    const newExecStatus = filters.exec_status?.[0] as ExecStatusType;
    const isStatusChanged =
      newExecStatus !== stateRef.current.currentExecStatus;

    stateRef.current = {
      ...stateRef.current,
      currentExecStatus: newExecStatus,
      pagination: {
        ...pagination,
        current: isStatusChanged ? 1 : pagination.current,
      },
    };
    setPaginationUI((prev) => ({
      ...prev,
      ...pagination,
      current: isStatusChanged ? 1 : pagination.current,
    }));

    fetchData();
  };

  const onTreeSelect = async (selectedKeys: any[]) => {
    if (selectedKeys.length > 0) {
      const nodeId = selectedKeys[0] as string;
      const node = findNodeById(treeData, nodeId);

      selectedRef.current = {
        nodeId,
        node,
      };

      setSearchTextUI('');
      stateRef.current.searchText = '';
      stateRef.current.currentExecStatus = undefined;
      setPaginationUI((prev) => ({ ...prev, current: 1 }));

      if (node?.tabItems?.length) {
        setActiveTab(node.tabItems[0].id);
        stateRef.current.activeTab = node.tabItems[0].id;
      } else {
        setActiveTab('');
        stateRef.current.activeTab = '';
      }
    }
  };

  const findNodeById = (
    nodes: TreeNode[],
    id: string
  ): TreeNode | undefined => {
    for (const node of nodes) {
      if (node.id === id) return node;
      if (node.children) {
        const found = findNodeById(node.children, id);
        if (found) return found;
      }
    }
    return undefined;
  };

  const handleCreate = () => {
    setEditingId(null);
    setDrawerVisible(true);
  };

  const handleEdit = (record: CollectTask) => {
    setEditingId(record.id);
    setDrawerVisible(true);
  };

  const handleDelete = (record: CollectTask) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        try {
          await collectApi.deleteCollect(record.id.toString());
          message.success(t('successfullyDeleted'));
          const currentPage = stateRef.current.pagination.current;
          if (currentPage > 1 && tableCountRef.current === 1) {
            stateRef.current.pagination.current = currentPage - 1;
            setPaginationUI((prev) => ({
              ...prev,
              current: currentPage - 1,
            }));
          }
          fetchData();
        } catch (error) {
          console.error('Failed to delete task:', error);
        }
      }
    });
  };

  const handleExecuteNow = useCallback(
    async (record: CollectTask) => {
      if (executingTaskIds.includes(record.id)) {
        return;
      }
      try {
        setExecutingTaskIds((prev) => [...prev, record.id]);
        await collectApi.executeCollect(record.id.toString());
        message.success(t('Collection.executeSuccess'));
        fetchData();
      } catch (error) {
        console.error('Failed to execute task:', error);
      } finally {
        setExecutingTaskIds((prev) => prev.filter((id) => id !== record.id));
      }
    },
    [executingTaskIds]
  );

  const closeDrawer = () => {
    setEditingId(null);
    setDrawerVisible(false);
  };

  const getTaskContent = () => {
    if (!selectedRef.current.node) return null;
    const modelItem = selectedRef.current.node.tabItems?.find(
      (item) => item.id === activeTab
    );
    if (!modelItem) return null;
    const props = {
      onClose: closeDrawer,
      onSuccess: fetchData,
      selectedNode: selectedRef.current.node,
      modelItem: modelItem as ModelItem,
      editId: editingId,
    };
    const taskMap: Record<string, React.ComponentType<any>> = {
      k8s: K8sTask,
      vmware: VMTask,
      network_topo: SNMPTask,
      network: SNMPTask,
      databases: SQLTask,
      cloud: CloudTask,
      host_manage: HostTask,
    };
    const TaskComponent = taskMap[selectedRef.current.nodeId] || K8sTask;
    return <TaskComponent {...props} />;
  };

  const toCamelCase = (str: string) => {
    return str
      .toLowerCase()
      .replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
  };

  const statusFilters = React.useMemo(() => {
    return Object.entries(EXEC_STATUS).map(([key, value]) => ({
      text: t(`Collection.execStatus.${toCamelCase(key)}`),
      value,
    }));
  }, [t]);

  const onSelectFields = async (fields: string[]) => {
    setDisplayFieldKeys(fields);
    const actionCol = allColumns.find((col) => col.key === 'action');
    const ordered = [
      ...allColumns
        .filter((col) => fields.includes(col.key as string))
        .sort(
          (a, b) =>
            fields.indexOf(a.key as string) - fields.indexOf(b.key as string)
        ),
      ...(actionCol ? [actionCol] : []),
    ] as ExtendedColumnItem[];
    setCurrentColumns(ordered);
  };

  const actionRender = useCallback(
    (record: CollectTask) => {
      const loadingExec = executingTaskIds.includes(record.id);
      const executing =
        record.exec_status === EXEC_STATUS.COLLECTING ||
        record.exec_status === EXEC_STATUS.WRITING ||
        loadingExec;

      return (
        <div className="flex gap-3">
          {record.input_method && !record.examine ? (
            <PermissionWrapper
              requiredPermissions={['Execute']}
              instPermissions={record.permission}
            >
              <Button
                type="link"
                size="small"
                disabled={executing}
                loading={loadingExec}
                onClick={() => handleApproval(record)}
              >
                {t('Collection.execStatus.approval')}
              </Button>
            </PermissionWrapper>
          ) : (
            <Button
              type="link"
              size="small"
              onClick={() => handleViewDetail(record)}
            >
              {t('Collection.table.detail')}
            </Button>
          )}

          <PermissionWrapper
            requiredPermissions={['Execute']}
            instPermissions={record.permission}
          >
            <Button
              type="link"
              size="small"
              disabled={executing}
              loading={loadingExec}
              onClick={() => handleExecuteNow(record)}
            >
              {loadingExec
                ? t('Collection.executing')
                : t('Collection.table.executeNow')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper
            requiredPermissions={['Edit']}
            instPermissions={record.permission}
          >
            <Button
              type="link"
              size="small"
              disabled={executing}
              onClick={() => handleEdit(record)}
            >
              {t('Collection.table.modify')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper
            requiredPermissions={['Delete']}
            instPermissions={record.permission}
          >
            <Button
              type="link"
              size="small"
              disabled={executing}
              onClick={() => handleDelete(record)}
            >
              {t('Collection.table.delete')}
            </Button>
          </PermissionWrapper>
        </div>
      );
    },
    [executingTaskIds, t]
  );

  const getColumns = useCallback(
    (): TableColumnType<CollectTask>[] => [
      {
        title: t('Collection.table.taskName'),
        dataIndex: 'name',
        key: 'name',
        fixed: 'left',
        width: 180,
        render: (text: any) => <span>{text || '--'}</span>,
      },
      {
        title: t('Collection.table.execStatus'),
        dataIndex: 'exec_status',
        key: 'exec_status',
        width: 160,
        filters: statusFilters,
        filterMultiple: false,
        render: (status: ExecStatusType) => {
          const config = execStatusConfig[status];
          return (
            <div className={styles.statusText}>
              <span
                className={styles.status}
                style={{ background: config.color }}
              />
              <span>{config.text}</span>
            </div>
          );
        },
      },
      {
        title: t('Collection.table.collectSummary'),
        dataIndex: 'collect_digest',
        key: 'collect_digest',
        width: 440,
        render: (_: any, record: CollectTask) => {
          const digest = (record.message || {}) as CollectTaskMessage;
          return Object.keys(digest).length > 0 ? (
            <div className="flex gap-2">
              {(
                Object.entries(ExecStatusMap) as [ExecStatusKey, ExecStatus][]
              ).map(([key, value]) => (
                <Tag key={key} color={value.color}>
                  {value.text}: {digest[key] ?? '--'}
                </Tag>
              ))}
            </div>
          ) : (
            <span>--</span>
          );
        },
      },
      {
        title: t('Collection.table.creator'),
        dataIndex: 'created_by',
        key: 'created_by',
        width: 120,
        render: (text: any) => <span>{text || '--'}</span>,
      },
      {
        title: t('Collection.table.execTime'),
        dataIndex: 'exec_time',
        key: 'exec_time',
        width: 220,
        render: (text: string) => (
          <span>{text ? dayjs(text).format('YYYY-MM-DD HH:mm:ss') : '--'}</span>
        ),
      },
      {
        title: t('Collection.table.actions'),
        dataIndex: 'action',
        key: 'action',
        fixed: 'right',
        width: 260,
        render: (_, record) => actionRender(record),
      },
    ],
    [t, actionRender]
  );

  const handleViewDetail = (record: CollectTask) => {
    setCurrentTask(record);
    setDetailVisible(true);
  };

  const handleApproval = async (record: CollectTask) => {
    setCurrentTask(record);
    setDetailVisible(true);
  };

  const getItems = (node: TreeNode) => {
    if (node.children?.[0]?.type) {
      node.tabItems = node.children;
      node.children = [];
    } else if (node.children) {
      node.children.forEach(getItems);
    }
  };

  useEffect(() => {
    const newColumns: any = getColumns();
    setAllColumns(newColumns);
    setDisplayFieldKeys(
      newColumns.map((col: TableColumnType) => col.key as string)
    );
    setCurrentColumns(newColumns);
  }, [executingTaskIds]);

  const hasMultipleTabs =
    (selectedRef.current?.node?.tabItems?.length ?? 0) > 1;

  const handleTabChange = (newActiveTab: string) => {
    setActiveTab(newActiveTab);
    stateRef.current.activeTab = newActiveTab;

    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    setSearchTextUI('');
    stateRef.current.searchText = '';
    stateRef.current.currentExecStatus = undefined;

    stateRef.current.pagination.current = 1;
    setPaginationUI((prev) => ({
      ...prev,
      current: 1,
    }));

    fetchData(true, newActiveTab);
  };

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="w-56 flex-shrink-0 border-r border-[var(--color-border-2)] pr-4 py-2 overflow-auto">
        <Spin spinning={treeLoading}>
          <Tree
            blockNode
            treeData={treeData}
            fieldNames={{ title: 'name', key: 'id', children: 'children' }}
            expandedKeys={expandedKeys}
            selectedKeys={[selectedRef.current.nodeId]}
            style={{ minHeight: '100px' }}
            onSelect={onTreeSelect}
          />
        </Spin>
      </div>
      <div className="flex-1 pt-1 pl-5 flex flex-col overflow-hidden">
        {hasMultipleTabs && (
          <Tabs
            activeKey={activeTab}
            items={selectedRef.current.node?.tabItems?.map((tab) => ({
              key: tab.id,
              label: tab.name,
            }))}
            onChange={handleTabChange}
          />
        )}
        <div className="mb-4 flex justify-between items-center flex-shrink-0">
          <Input
            placeholder={t('Collection.inputTaskPlaceholder')}
            prefix={<SearchOutlined className="text-gray-400" />}
            className={'w-72'}
            allowClear
            value={searchTextUI}
            onChange={handleSearchChange}
            onPressEnter={handleEnterSearch}
            onClear={handleClearSearch}
          />
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button
              type="primary"
              className="!rounded-button whitespace-nowrap"
              onClick={handleCreate}
            >
              {t('Collection.addTaskTitle')}
            </Button>
          </PermissionWrapper>
        </div>
        <div className="rounded-lg shadow-sm flex-1 overflow-auto">
          <CustomTable
            loading={tableLoading}
            key={selectedRef.current.nodeId}
            size="middle"
            rowKey="id"
            columns={currentColumns}
            dataSource={tableData}
            scroll={{
              y: hasMultipleTabs
                ? 'calc(100vh - 510px)'
                : 'calc(100vh - 450px)',
            }}
            onSelectFields={onSelectFields}
            onChange={handleTableChange}
            pagination={{
              ...paginationUI,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条`,
            }}
            fieldSetting={{
              showSetting: true,
              displayFieldKeys,
              choosableFields: allColumns.filter(
                (item): item is ColumnItem =>
                  item.key !== 'action' && 'dataIndex' in item
              ),
            }}
          />
        </div>
      </div>

      <Drawer
        title={
          editingId
            ? t('Collection.editTaskTitle')
            : t('Collection.addTaskTitle')
        }
        placement="right"
        width={640}
        onClose={closeDrawer}
        open={drawerVisible}
      >
        {drawerVisible && getTaskContent()}
      </Drawer>

      <Drawer
        title={
          currentTask?.input_method && !currentTask?.examine
            ? t('Collection.taskDetail.approval')
            : t('Collection.taskDetail.title')
        }
        placement="right"
        width={750}
        onClose={() => setDetailVisible(false)}
        open={detailVisible}
      >
        {detailVisible && currentTask && (
          <TaskDetail
            task={currentTask}
            modelId={selectedRef.current.nodeId}
            onClose={() => setDetailVisible(false)}
            onSuccess={fetchData}
          />
        )}
      </Drawer>
    </div>
  );
};

export default ProfessionalCollection;
