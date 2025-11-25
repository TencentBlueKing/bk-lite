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
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import type { TableColumnType } from 'antd';
import type { ColumnItem } from '@/app/cmdb/types/assetManage';
import type { ColumnType } from 'antd/es/table';
import { Modal } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { Input, Button, Spin, Tag, Drawer, message, Tabs, Card } from 'antd';
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
import MarkdownRenderer from '@/components/markdown';

type ExtendedColumnItem = ColumnType<CollectTask> & {
  key: string;
  dataIndex?: string;
};

const ProfessionalCollection: React.FC = () => {
  const { t } = useTranslation();
  const collectApi = useCollectApi();
  const ExecStatusMap = React.useMemo(() => createExecStatusMap(t), [t]);
  const syncStatusConfig = React.useMemo(() => getExecStatusConfig(t), [t]);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [treeData, setTreeData] = useState<TreeNode[]>([]);
  const [detailVisible, setDetailVisible] = useState(false);
  const [currentTask, setCurrentTask] = useState<CollectTask | null>(null);
  const [activeTab, setActiveTab] = useState<string>('');
  const [tableData, setTableData] = useState<CollectTask[]>([]);
  const [displayFieldKeys, setDisplayFieldKeys] = useState<string[]>([]);
  const [allColumns, setAllColumns] = useState<ExtendedColumnItem[]>([]);
  const [currentColumns, setCurrentColumns] = useState<ExtendedColumnItem[]>(
    []
  );
  const [treeLoading, setTreeLoading] = useState(false);
  const [tableLoading, setTableLoading] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [executingTaskIds, setExecutingTaskIds] = useState<number[]>([]);
  const [docDrawerVisible, setDocDrawerVisible] = useState(false);
  const [taskDocDrawerVisible, setTaskDocDrawerVisible] = useState(false);
  const [pluginDoc, setPluginDoc] = useState<string>('');
  const [docLoading, setDocLoading] = useState(false);
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

  const currentPlugin = React.useMemo(() => {
    return selectedRef.current.node?.tabItems?.find(
      (item) => item.id === activeTab
    );
  }, [activeTab]);

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
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
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

      setPluginDoc('');
      setDocLoading(false);

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

  const fetchPluginDoc = async (pluginId: string) => {
    try {
      setDocLoading(true);
      const data = await collectApi.getCollectModelDoc(pluginId);
      setPluginDoc(data || '');
    } catch (error) {
      console.error('Failed to fetch plugin doc:', error);
      setPluginDoc('');
      message.error('获取插件文档失败');
    } finally {
      setDocLoading(false);
    }
  };

  const handleViewDoc = () => {
    if (activeTab && !pluginDoc) {
      fetchPluginDoc(activeTab);
    }
    setDocDrawerVisible(true);
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
      },
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
    setTaskDocDrawerVisible(false);
  };

  const getTaskContent = () => {
    if (!selectedRef.current.node || !currentPlugin) return null;
    const props = {
      onClose: closeDrawer,
      onSuccess: fetchData,
      selectedNode: selectedRef.current.node,
      modelItem: currentPlugin as ModelItem,
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
      text: t(`Collection.syncStatus.${toCamelCase(key)}`),
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
                {t('Collection.syncStatus.approval')}
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
                ? t('Collection.table.syncing')
                : t('Collection.table.sync')}
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
        title: t('Collection.table.syncStatus'),
        dataIndex: 'exec_status',
        key: 'exec_status',
        width: 160,
        filters: statusFilters,
        filterMultiple: false,
        render: (status: ExecStatusType) => {
          const config = syncStatusConfig[status];
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
        title: t('Collection.table.syncTime'),
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

    setPluginDoc('');
    setDocLoading(false);

    fetchData(true, newActiveTab);
  };

  const PluginCard = ({ tab }: { tab: any }) => {
    const isActive = activeTab === tab.id;
    const tags = tab.tag || [];
    const description = tab.desc || '';

    return (
      <Card
        key={tab.id}
        hoverable
        className={`cursor-pointer transition-all ${
          isActive
            ? 'border-blue-500 shadow-md bg-blue-50'
            : 'border-gray-200 hover:border-blue-300'
        }`}
        bodyStyle={{ padding: '14px' }}
        onClick={() => handleTabChange(tab.id)}
      >
        <div className="flex items-start gap-3 mb-2">
          <div
            className={`w-10 h-10 rounded flex items-center justify-center text-lg font-semibold flex-shrink-0 ${
              isActive ? 'bg-blue-500 text-white' : 'bg-blue-100 text-blue-600'
            }`}
          >
            {tab.name?.charAt(0)}
          </div>
          <div className="flex-1 min-w-0">
            <div
              className={`text-sm font-medium mb-1 ${
                isActive ? 'text-blue-600' : 'text-gray-800'
              }`}
            >
              {tab.name}
            </div>
            <div className="text-xs text-gray-500">
              <EllipsisWithTooltip
                text={description}
                className="line-clamp-3"
              />
            </div>
          </div>
        </div>
        {tags.length > 0 && (
          <div className="pt-2 mt-2 border-t border-gray-200 flex flex-wrap gap-1.5">
            {tags.map((tag: string) => (
              <Tag
                key={tag}
                color="blue"
                style={{
                  fontSize: '10px',
                  padding: '0 4px',
                  lineHeight: '16px',
                  margin: 0,
                  borderRadius: '2px',
                }}
              >
                {tag}
              </Tag>
            ))}
          </div>
        )}
      </Card>
    );
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="bg-white border-b border-gray-200 ml-2">
        {treeLoading ? (
          <div className="flex items-center justify-center py-2">
            <Spin size="small" />
          </div>
        ) : (
          <Tabs
            activeKey={selectedRef.current.nodeId}
            onChange={(key) => onTreeSelect([key])}
            items={treeData.map((category) => ({
              key: category.id,
              label: category.name,
            }))}
          />
        )}
      </div>

      <div className="flex flex-1 overflow-hidden pt-4">
        <div className="w-56 flex-shrink-0 h-full">
          {treeLoading ? (
            <div className="flex items-center justify-center py-4">
              <Spin size="small" />
            </div>
          ) : (
            <div className="space-y-3 px-2 py-1 overflow-auto h-full">
              {selectedRef.current.node?.tabItems?.map((tab) => (
                <PluginCard key={tab.id} tab={tab} />
              ))}
            </div>
          )}
        </div>

        <div className="w-px bg-gray-200 flex-shrink-0 mr-2"></div>

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex flex-col flex-1 overflow-hidden bg-white rounded shadow-sm border border-gray-200">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
              <span className="text-base font-semibold text-gray-900">
                {currentPlugin?.name || ''}
              </span>
              <span className="text-sm text-gray-400">
                {currentPlugin?.desc || ''}
              </span>
              <Button
                type="link"
                size="small"
                className="ml-2"
                onClick={handleViewDoc}
              >
                {t('Collection.viewDoc')}
              </Button>
            </div>

            <div className="px-4 py-4 flex justify-between items-center">
              <Input
                placeholder={t('Collection.inputTaskPlaceholder')}
                prefix={<SearchOutlined className="text-gray-400" />}
                className="w-80"
                allowClear
                value={searchTextUI}
                onChange={handleSearchChange}
                onPressEnter={handleEnterSearch}
                onClear={handleClearSearch}
              />
              <PermissionWrapper requiredPermissions={['Add']}>
                <Button type="primary" onClick={handleCreate}>
                  {t('Collection.addTaskTitle')}
                </Button>
              </PermissionWrapper>
            </div>

            <div className="flex-1 overflow-hidden p-4 pt-1">
              <CustomTable
                loading={tableLoading}
                key={selectedRef.current.nodeId}
                size="middle"
                rowKey="id"
                columns={currentColumns}
                dataSource={tableData}
                scroll={{
                  y: 'calc(100vh - 600px)',
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
        </div>
      </div>

      <Drawer
        title={
          <div className="flex items-center justify-between">
            <span>
              {editingId
                ? t('Collection.editTaskTitle')
                : t('Collection.addTaskTitle')}
            </span>
            <Button
              type="link"
              size="small"
              onClick={() => {
                if (!taskDocDrawerVisible && activeTab && !pluginDoc) {
                  fetchPluginDoc(activeTab);
                }
                setTaskDocDrawerVisible(!taskDocDrawerVisible);
              }}
            >
              {taskDocDrawerVisible
                ? t('Collection.closeDoc')
                : t('Collection.viewDoc')}
            </Button>
          </div>
        }
        placement="right"
        width={640}
        onClose={closeDrawer}
        open={drawerVisible}
        getContainer={false}
        style={{ position: 'absolute' }}
      >
        {drawerVisible && getTaskContent()}
      </Drawer>

      <Drawer
        title={t('Collection.pluginDoc')}
        placement="right"
        width={600}
        onClose={() => {
          setTaskDocDrawerVisible(false);
          setDocDrawerVisible(false);
        }}
        open={docDrawerVisible || (taskDocDrawerVisible && drawerVisible)}
        getContainer={taskDocDrawerVisible && drawerVisible ? false : undefined}
        styles={{
          wrapper: {
            boxShadow:
              taskDocDrawerVisible && drawerVisible ? 'none' : undefined,
            borderRight:
              taskDocDrawerVisible && drawerVisible
                ? '1px solid var(--color-border-1)'
                : undefined,
          },
        }}
        style={
          taskDocDrawerVisible && drawerVisible
            ? { position: 'absolute' }
            : undefined
        }
        mask={taskDocDrawerVisible && drawerVisible ? false : true}
        rootStyle={
          taskDocDrawerVisible && drawerVisible
            ? {
              left: 'auto',
              right: '640px',
            }
            : undefined
        }
        footer={
          <div className="flex justify-start">
            <Button
              onClick={() => {
                setTaskDocDrawerVisible(false);
                setDocDrawerVisible(false);
              }}
            >
              {t('common.close')}
            </Button>
          </div>
        }
      >
        {docLoading ? (
          <div className="flex items-center justify-center py-6">
            <Spin />
          </div>
        ) : (
          <MarkdownRenderer content={pluginDoc} />
        )}
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
