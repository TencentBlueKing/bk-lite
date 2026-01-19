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
import MarkdownRenderer from '@/components/markdown';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import { useCollectApi } from '@/app/cmdb/api';
import type { TableColumnType, TablePaginationConfig } from 'antd';
import type { ColumnItem } from '@/app/cmdb/types/assetManage';
import type { ColumnType } from 'antd/es/table';
import type { FilterValue } from 'antd/es/table/interface';
import { Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  Input,
  Button,
  Spin,
  Tag,
  Drawer,
  message,
  Tabs,
  Card,
  Tooltip,
} from 'antd';
import {
  getExecStatusConfig,
  EXEC_STATUS,
  ExecStatusType,
} from '@/app/cmdb/constants/professCollection';
import {
  CollectTask,
  TreeNode,
  CollectTaskMessage,
  ModelItem,
  TaskStatusMap,
} from '@/app/cmdb/types/autoDiscovery';
import { useAssetManageStore } from '@/app/cmdb/store';

type ExtendedColumnItem = ColumnType<CollectTask> & {
  key: string;
  dataIndex?: string;
};

interface PluginCardProps {
  tab: TreeNode;
}

const ProfessionalCollection: React.FC = () => {
  const { t } = useTranslation();
  const collectApi = useCollectApi();
  const { editingId, setEditingId } = useAssetManageStore();
  const syncStatusConfig = React.useMemo(() => getExecStatusConfig(t), [t]);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [categoryList, setCategoryList] = useState<TreeNode[]>([]);
  const [detailVisible, setDetailVisible] = useState(false);
  const [currentTask, setCurrentTask] = useState<CollectTask | null>(null);
  const [selectedPluginId, setSelectedPluginId] = useState<string>('');
  const [tableData, setTableData] = useState<CollectTask[]>([]);
  const [displayFieldKeys, setDisplayFieldKeys] = useState<string[]>([]);
  const [allColumns, setAllColumns] = useState<ExtendedColumnItem[]>([]);
  const [currentColumns, setCurrentColumns] = useState<ExtendedColumnItem[]>(
    []
  );
  const [categoryLoading, setCategoryLoading] = useState(false);
  const [tableLoading, setTableLoading] = useState(false);
  const [executingTaskIds, setExecutingTaskIds] = useState<number[]>([]);
  const [docDrawerVisible, setDocDrawerVisible] = useState(false);
  const [taskDocDrawerVisible, setTaskDocDrawerVisible] = useState(false);
  const [pluginDoc, setPluginDoc] = useState<string>('');
  const [docLoading, setDocLoading] = useState(false);
  const [taskStatus, setTaskStatus] = useState<TaskStatusMap>({});
  const tableCountRef = useRef<number>(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const statusTimerRef = useRef<NodeJS.Timeout | null>(null);
  const stateRef = useRef({
    searchText: '',
    pagination: {
      current: 1,
      pageSize: 20,
      total: 0,
    },
    currentExecStatus: undefined as ExecStatusType | undefined,
    selectedPluginId: '',
  });
  const selectedCategoryRef = useRef<{
    categoryId: string;
    category?: TreeNode;
  }>({ categoryId: '' });
  const [searchTextUI, setSearchTextUI] = useState('');
  const [paginationUI, setPaginationUI] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });

  const currentPlugin = React.useMemo(() => {
    return selectedCategoryRef.current.category?.tabItems?.find(
      (item) => item.id === selectedPluginId
    );
  }, [selectedPluginId]);

  const getParams = (pluginId?: string) => {
    const modelId = pluginId || stateRef.current.selectedPluginId;

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

  const fetchData = async (showLoading = true, pluginId?: string) => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    try {
      if (!selectedCategoryRef.current.categoryId) return;
      if (showLoading) {
        setTableLoading(true);
      }
      const params = getParams(pluginId);
      const data = (await collectApi.getCollectList(params)) as {
        items: CollectTask[];
        count: number;
      };
      // console.log('test2.4:getCollectList', data);
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
      resetTimer(pluginId);
    }
  };

  const resetTimer = (pluginId?: string) => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    const currentPluginId = pluginId || stateRef.current.selectedPluginId;
    timerRef.current = setTimeout(
      () => fetchData(false, currentPluginId),
      30 * 1000
    );
  };

  const fetchTaskStatus = async () => {
    try {
      const data = (await collectApi.getTaskStatus()) as TaskStatusMap;
      setTaskStatus(data || {});
    } catch (error) {
      console.error('Failed to fetch task status:', error);
    }
  };

  const fetchCategoryData = async () => {
    try {
      setCategoryLoading(true);
      const data = await collectApi.getCollectModelTree();
      const categories = data.map((node: TreeNode) => {
        getItems(node);
        return node;
      });

      const allCategory: TreeNode = {
        id: 'all',
        key: 'all',
        name: '全部',
        tabItems: categories.flatMap((node: TreeNode) => node.tabItems || []),
      };

      setCategoryList([allCategory, ...categories]);
      if (!data.length) return;

      selectedCategoryRef.current = {
        categoryId: 'all',
        category: allCategory,
      };

      const firstPlugin = allCategory.tabItems?.[0];
      if (firstPlugin) {
        setSelectedPluginId(firstPlugin.id);
        stateRef.current.selectedPluginId = firstPlugin.id;
        fetchData(true, firstPlugin.id);
      }

      fetchTaskStatus();
    } catch (error) {
      console.error('Failed to fetch tree data:', error);
    } finally {
      setCategoryLoading(false);
    }
  };

  useEffect(() => {
    fetchCategoryData();

    statusTimerRef.current = setInterval(() => {
      fetchTaskStatus();
    }, 30 * 1000);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (statusTimerRef.current) {
        clearInterval(statusTimerRef.current);
        statusTimerRef.current = null;
      }
    };
  }, []);

  const handleSearch = (value: string) => {
    setSearchTextUI(value);
    stateRef.current.searchText = value;
    stateRef.current.pagination.current = 1;
    setPaginationUI((prev) => ({ ...prev, current: 1 }));
    fetchData();
  };

  const handleTableChange = (
    pagination: TablePaginationConfig,
    filters: Record<string, FilterValue | null>
  ) => {
    const newExecStatus = filters.exec_status?.[0] as ExecStatusType;
    const isStatusChanged =
      newExecStatus !== stateRef.current.currentExecStatus;

    const currentPage = isStatusChanged ? 1 : (pagination.current ?? 1);
    const pageSize = pagination.pageSize ?? 20;

    stateRef.current = {
      ...stateRef.current,
      currentExecStatus: newExecStatus,
      pagination: {
        current: currentPage,
        pageSize,
        total: stateRef.current.pagination.total,
      },
    };
    setPaginationUI((prev) => ({
      ...prev,
      current: currentPage,
      pageSize,
    }));

    fetchData();
  };

  const handleCategoryChange = async (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      const categoryId = selectedKeys[0] as string;
      const category = categoryList.find((cat) => cat.id === categoryId);

      selectedCategoryRef.current = {
        categoryId,
        category,
      };

      setSearchTextUI('');
      stateRef.current.searchText = '';
      stateRef.current.currentExecStatus = undefined;
      setPaginationUI((prev) => ({ ...prev, current: 1 }));
      stateRef.current.pagination.current = 1;

      setPluginDoc('');
      setDocLoading(false);

      if (category?.tabItems?.length) {
        const firstPluginId = category.tabItems[0].id;
        setSelectedPluginId(firstPluginId);
        stateRef.current.selectedPluginId = firstPluginId;
        fetchData(true, firstPluginId);
      } else {
        setSelectedPluginId('');
        stateRef.current.selectedPluginId = '';
        setTableData([]);
      }
    }
  };

  const handleCreate = () => {
    // console.log('test2.1');
    setEditingId(null);
    setDrawerVisible(true);
  };

  const fetchPluginDoc = async (pluginId: string) => {
    try {
      setDocLoading(true);
      const data = await collectApi.getCollectModelDoc(pluginId);
      setPluginDoc(data || '');
    } catch {
      setPluginDoc('');
    } finally {
      setDocLoading(false);
    }
  };

  const handleViewDoc = () => {
    if (selectedPluginId && !pluginDoc) {
      fetchPluginDoc(selectedPluginId);
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

  const findParentCategoryByPluginId = (
    pluginId: string
  ): TreeNode | undefined => {
    for (const category of categoryList) {
      if (category.id === 'all') continue;
      if (category.tabItems?.some((item) => item.id === pluginId)) {
        return category;
      }
    }
    return undefined;
  };

  const getTaskContent = () => {
    // console.log('test2.2', selectedCategoryRef.current.category, currentPlugin);
    if (!selectedCategoryRef.current.category || !currentPlugin) return null;

    const actualCategory =
      selectedCategoryRef.current.categoryId === 'all'
        ? findParentCategoryByPluginId(selectedPluginId)
        : selectedCategoryRef.current.category;

    if (!actualCategory) return null;

    const props = {
      onClose: closeDrawer,
      onSuccess: fetchData,
      selectedNode: actualCategory,
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
      middleware: HostTask,
    };
    const TaskComponent = taskMap[actualCategory.id] || K8sTask;
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

  const onSelectFields = (fields: string[]) => {
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
          <Button
            type="link"
            size="small"
            onClick={() => handleViewDetail(record)}
          >
            {t('Collection.table.detail')}
          </Button>

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
        render: (text: string) => <span>{text || '--'}</span>,
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
        title: t('Collection.table.latestOverview'),
        dataIndex: 'collect_digest',
        key: 'collect_digest',
        width: 400,
        render: (_value, record: CollectTask) => {
          const digest = (record.message || {}) as CollectTaskMessage;

          if (record.exec_status === EXEC_STATUS.ERROR && digest.message) {
            return (
              <Tooltip title={digest.message}>
                <div className={`${styles.ellipsis2Lines} text-gray-500`}>
                  {digest.message}
                </div>
              </Tooltip>
            );
          }

          const errorTotal =
            (digest.add_error || 0) +
            (digest.delete_error || 0) +
            (digest.update_error || 0);

          return Object.keys(digest).length > 0 ? (
            <div className="flex gap-2">
              <Tag color="blue">
                {t('Collection.overviewLabel.add')}:{' '}
                {digest.add_success ?? '--'}
              </Tag>
              <Tag color="orange">
                {t('Collection.overviewLabel.update')}:{' '}
                {digest.update_success ?? '--'}
              </Tag>
              <Tag color="volcano">
                {t('Collection.overviewLabel.delete')}:{' '}
                {digest.delete_success ?? '--'}
              </Tag>
              {errorTotal > 0 && (
                <Tag color="red">
                  {t('Collection.overviewLabel.error')}: {errorTotal}
                </Tag>
              )}
            </div>
          ) : (
            <span>--</span>
          );
        },
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
        title: t('Collection.table.reportTime'),
        dataIndex: 'last_time',
        key: 'last_time',
        width: 220,
        render: (_, record: CollectTask) => {
          const lastTime = (record.message as CollectTaskMessage)?.last_time;
          return (
            <span>{lastTime ? dayjs(lastTime).format('YYYY-MM-DD HH:mm:ss') : '--'}</span>
          );
        },
      },
      {
        title: t('Collection.table.creator'),
        dataIndex: 'created_by',
        key: 'created_by',
        width: 120,
        render: (text: string) => <span>{text || '--'}</span>,
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

  const getItems = (node: TreeNode) => {
    if (node.children?.[0]?.type) {
      node.tabItems = node.children;
      node.children = [];
    } else if (node.children) {
      node.children.forEach(getItems);
    }
  };

  useEffect(() => {
    const newColumns = getColumns() as ExtendedColumnItem[];
    setAllColumns(newColumns);
    setDisplayFieldKeys(newColumns.map((col) => col.key as string));
    setCurrentColumns(newColumns);
  }, [executingTaskIds]);

  const handlePluginCardClick = (pluginId: string) => {
    setSelectedPluginId(pluginId);
    stateRef.current.selectedPluginId = pluginId;

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

    fetchData(true, pluginId);
  };

  const PluginCard: React.FC<PluginCardProps> = ({ tab }) => {
    const isActive = selectedPluginId === tab.id;
    const tags = tab.tag || [];
    const description = tab.desc || '';

    const taskStats = taskStatus[tab.model_id || tab.id] || {
      running: 0,
      success: 0,
      failed: 0,
    };

    const statusItems = [
      {
        color: 'bg-blue-500',
        label: t('Collection.statusLabel.running'),
        value: taskStats.running,
      },
      {
        color: 'bg-green-500',
        label: t('Collection.statusLabel.syncSuccess'),
        value: taskStats.success,
      },
      {
        color: 'bg-red-500',
        label: t('Collection.statusLabel.syncFailed'),
        value: taskStats.failed,
      },
    ];

    return (
      <Card
        key={tab.id}
        hoverable
        className={`cursor-pointer transition-all ${isActive
          ? 'border-blue-500 shadow-md bg-blue-50'
          : 'border-gray-200 hover:border-blue-300'
        }`}
        styles={{ body: { padding: '12px' } }}
        onClick={() => handlePluginCardClick(tab.id)}
      >
        <div className="flex items-center gap-3 mb-2">
          <div
            className={`w-10 h-10 rounded flex items-center justify-center text-lg font-semibold flex-shrink-0 ${isActive ? 'bg-blue-500 text-white' : 'bg-blue-100 text-blue-600'}`}
          >
            {tab.name?.charAt(0)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-gray-700 mb-2 leading-relaxed">
              <span
                className={`font-semibold ${isActive ? 'text-blue-600' : 'text-gray-900'}`}
              >
                {tab.name}
              </span>
              {description && (
                <span className="text-gray-500 ml-1">{description}</span>
              )}
            </div>
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
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
          </div>
        </div>

        <Tooltip
          placement="left"
          title={
            <div className="flex flex-col gap-1">
              {statusItems.map(({ label, value, color }) => (
                <div key={label} className="flex items-center gap-2 text-xs">
                  <div className={`w-2 h-2 rounded-full ${color}`} />
                  <span>
                    {label}：{value}
                  </span>
                </div>
              ))}
            </div>
          }
        >
          <div
            className="flex items-center justify-around pt-2 mt-3 border-t"
            style={{ borderColor: 'var(--color-border-2)' }}
            onClick={(e) => e.stopPropagation()}
          >
            {statusItems.map(({ color, value }, index) => (
              <div key={index} className="flex items-center gap-1.5">
                <div
                  className={`w-2 h-2 rounded-full ${color} ring-2 ring-white shadow-sm`}
                />
                <span className="text-sm font-medium">{value}</span>
              </div>
            ))}
          </div>
        </Tooltip>
      </Card>
    );
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="bg-white border-b border-gray-200 ml-2">
        {categoryLoading ? (
          <div className="flex items-center justify-center py-2">
            <Spin size="small" />
          </div>
        ) : (
          <Tabs
            activeKey={selectedCategoryRef.current.categoryId}
            onChange={(key) => handleCategoryChange([key])}
            items={categoryList.map((category) => {
              return {
                key: category.id,
                label: category.name,
              };
            })}
          />
        )}
      </div>

      <div className="flex flex-1 overflow-hidden pt-4">
        <div className="w-60 flex-shrink-0 h-full">
          {categoryLoading ? (
            <div className="flex items-center justify-center py-4">
              <Spin size="small" />
            </div>
          ) : (
            <div className="flex flex-col gap-3 px-2 py-1 overflow-auto h-full">
              {selectedCategoryRef.current.category?.tabItems?.map((tab) => (
                <PluginCard key={tab.id} tab={tab} />
              ))}
            </div>
          )}
        </div>

        <div
          className="w-px flex-shrink-0 mr-2"
          style={{ backgroundColor: 'var(--color-border-2)' }}
        ></div>

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
              <Input.Search
                placeholder={t('Collection.inputTaskPlaceholder')}
                className="w-80"
                allowClear
                value={searchTextUI}
                onChange={(e) => setSearchTextUI(e.target.value)}
                onSearch={handleSearch}
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
                key={selectedCategoryRef.current.categoryId}
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
      {/* 编辑任务弹窗 */}
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
                if (!taskDocDrawerVisible && selectedPluginId && !pluginDoc) {
                  fetchPluginDoc(selectedPluginId);
                }
                setTaskDocDrawerVisible(!taskDocDrawerVisible);
              }}
            >
              {taskDocDrawerVisible
                ? t('Collection.closeDoc')
                : t('Collection.viewDoc')
              }
            </Button>
          </div>
        }
        placement="right"
        width={640}
        onClose={closeDrawer}
        open={drawerVisible}
        getContainer={false}
        rootStyle={{
          position: 'fixed',
        }}
      >
        {/* 渲染任务内容 */}
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
        mask={taskDocDrawerVisible && drawerVisible ? false : true}
        rootStyle={
          taskDocDrawerVisible && drawerVisible
            ? {
              position: 'absolute',
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
        title={t('Collection.taskDetail.title')}
        placement="right"
        width={750}
        onClose={() => setDetailVisible(false)}
        open={detailVisible}
        footer={
          <div className="flex justify-start">
            <Button onClick={() => setDetailVisible(false)}>
              {t('common.close')}
            </Button>
          </div>
        }
      >
        {detailVisible && currentTask && (
          <TaskDetail
            task={currentTask}
            modelId={selectedCategoryRef.current.categoryId}
            onClose={() => setDetailVisible(false)}
            onSuccess={fetchData}
          />
        )}
      </Drawer>
    </div>
  );
};

export default ProfessionalCollection;
