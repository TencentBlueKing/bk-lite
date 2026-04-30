'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import dayjs from 'dayjs';
import Image from 'next/image';
import styles from './index.module.scss';
import K8sTask from './components/k8sTask';
import VMTask from './components/vmTask';
import SNMPTask from './components/snmpTask';
import SQLTask from './components/sqlTask';
import CloudTask from './components/cloudTask';
import HostTask from './components/hostTask';
import IPMITask from './components/ipmiTask';
import ConfigFileTask from './components/configFileTask';
import TaskDetail from './components/taskDetail';
import { getCollectionIconSrc } from './collectionIcons';
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
import { Input, Button, Spin, Tag, Drawer, message, Tabs, Tooltip } from 'antd';
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
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

type ExtendedColumnItem = ColumnType<CollectTask> & {
  key: string;
  dataIndex?: string;
};

interface PluginCardProps {
  tab: TreeNode;
}

interface ExpandableTextProps {
  text?: string;
  collapsedLines?: 2 | 3;
}

const ExpandableText: React.FC<ExpandableTextProps> = ({
  text,
  collapsedLines = 3,
}) => {
  if (!text) {
    return null;
  }

  return (
    <div
      className={`mt-1.5 text-xs leading-5 text-slate-500 ${collapsedLines === 3 ? 'line-clamp-3' : 'line-clamp-2'}`}
    >
      {text}
    </div>
  );
};

const ProfessionalCollection: React.FC = () => {
  const { t } = useTranslation();
  const collectApi = useCollectApi();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const editingId = useAssetManageStore((state) => state.editingId);
  const setEditingId = useAssetManageStore((state) => state.setEditingId);
  const setCopyTaskData = useAssetManageStore((state) => state.setCopyTaskData);
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
  const isSyncingTaskDetailRef = useRef(false);
  const isClosingTaskDetailRef = useRef(false);
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

  const buildTargetUrl = useCallback(
    (next: {
      categoryId?: string | null;
      pluginId?: string | null;
      taskId?: string | null;
    }) => {
      const params = new URLSearchParams(searchParams.toString());
      if (next.categoryId !== undefined) {
        if (next.categoryId) {
          params.set('category', next.categoryId);
        } else {
          params.delete('category');
        }
      }
      if (next.pluginId !== undefined) {
        if (next.pluginId) {
          params.set('plugin', next.pluginId);
        } else {
          params.delete('plugin');
        }
      }
      if (next.taskId !== undefined) {
        if (next.taskId) {
          params.set('taskId', next.taskId);
        } else {
          params.delete('taskId');
        }
      }

      const query = params.toString();
      return query ? `${pathname}?${query}` : pathname;
    },
    [pathname, searchParams]
  );

  const syncUrlState = useCallback(
    (
      next: {
        categoryId?: string | null;
        pluginId?: string | null;
        taskId?: string | null;
      },
      mode: 'replace' | 'push' = 'replace'
    ) => {
      const targetUrl = buildTargetUrl(next);
      const currentQuery = searchParams.toString();
      const currentUrl = currentQuery ? `${pathname}?${currentQuery}` : pathname;

      if (targetUrl === currentUrl) {
        return;
      }

      if (mode === 'push') {
        router.push(targetUrl, { scroll: false });
        return;
      }

      router.replace(targetUrl, { scroll: false });
    },
    [buildTargetUrl, pathname, router, searchParams]
  );

  const openTaskDetailById = useCallback(
    async (taskId: string) => {
      if (!taskId) {
        return;
      }
      try {
        const taskDetail = (await collectApi.getCollectDetail(taskId)) as CollectTask;
        setCurrentTask(taskDetail);
        setDetailVisible(true);
      } catch {
        message.warning(t('Collection.taskDetail.title'));
        syncUrlState({ taskId: null }, 'replace');
      }
    },
    [collectApi, syncUrlState, t]
  );

  const currentPlugin = React.useMemo(() => {
    return selectedCategoryRef.current.category?.tabItems?.find(
      (item) => item.id === selectedPluginId
    );
  }, [selectedPluginId]);

  const getParams = (pluginId?: string) => {
    const currentPluginId = pluginId || stateRef.current.selectedPluginId;
    const plugin = selectedCategoryRef.current.category?.tabItems?.find(
      (item) => item.id === currentPluginId
    );

    return {
      page: stateRef.current.pagination.current,
      page_size: stateRef.current.pagination.pageSize,
      model_id: plugin?.model_id || currentPluginId,
      ...(plugin?.type && { driver_type: plugin.type }),
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

      const urlCategoryId = searchParams.get('category') || 'all';
      const matchedCategory = [allCategory, ...categories].find(
        (category) => category.id === urlCategoryId
      );
      const resolvedCategory = matchedCategory || allCategory;

      const urlPluginId = searchParams.get('plugin') || '';
      const pluginInCategory = resolvedCategory.tabItems?.find(
        (item) => item.id === urlPluginId
      );
      const resolvedPluginId = pluginInCategory
        ? pluginInCategory.id
        : (resolvedCategory.tabItems?.[0]?.id || '');

      selectedCategoryRef.current = {
        categoryId: resolvedCategory.id,
        category: resolvedCategory,
      };

      if (resolvedPluginId) {
        setSelectedPluginId(resolvedPluginId);
        stateRef.current.selectedPluginId = resolvedPluginId;
        await fetchData(true, resolvedPluginId);
      } else {
        setSelectedPluginId('');
        stateRef.current.selectedPluginId = '';
        setTableData([]);
      }

      syncUrlState(
        {
          categoryId: resolvedCategory.id,
          pluginId: resolvedPluginId || null,
        },
        'replace'
      );

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
        await fetchData(true, firstPluginId);
        syncUrlState(
          {
            categoryId,
            pluginId: firstPluginId,
            taskId: null,
          },
          'replace'
        );
      } else {
        setSelectedPluginId('');
        stateRef.current.selectedPluginId = '';
        setTableData([]);
        syncUrlState(
          {
            categoryId,
            pluginId: null,
            taskId: null,
          },
          'replace'
        );
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
      const plugin = selectedCategoryRef.current.category?.tabItems?.find(
        (item) => item.id === pluginId
      );
      const data = await collectApi.getCollectModelDoc(plugin?.model_id || pluginId);
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


  // 复制任务
  const handleCopy = async (record: CollectTask) => {
    try {
      const data = await collectApi.getCollectDetail(record.id.toString());
      setCopyTaskData(data);
      setEditingId(null);
      setDrawerVisible(true);
    } catch (error) {
      console.error('Failed to fetch task details:', error);
    }
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
    setEditingId(null);// 编辑任务数据置空
    setCopyTaskData(null); // 复制任务数据置空
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

    if (!currentPlugin) return null;

    const actualCategory =
      selectedCategoryRef.current.categoryId === 'all'
        ? findParentCategoryByPluginId(currentPlugin.id)
        : selectedCategoryRef.current.category;

    if (!actualCategory) return null;

    const taskProps = {
      onClose: closeDrawer,
      onSuccess: fetchData,
      selectedNode: actualCategory,
      modelItem: currentPlugin as ModelItem,
      editId: editingId,
    };

      const taskMap: Record<string, React.ComponentType<any>> = {
        k8s: K8sTask,
        vm: VMTask,
        cloud: CloudTask,
        host: HostTask,
        db: HostTask,
        middleware: HostTask,
        config_file: ConfigFileTask,
        snmp: SNMPTask,
        protocol: SQLTask,
      };

    if (currentPlugin.id === 'physcial_server_ipmi') {
      return <IPMITask {...taskProps} />;
    }

    const taskTypeKey = currentPlugin.task_type || currentPlugin.type || actualCategory.id;
    const TaskComponent = taskMap[taskTypeKey] || K8sTask;

    return <TaskComponent {...taskProps} />;
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
          {/* 复制任务按钮 */}
          <PermissionWrapper
            requiredPermissions={['Edit']}
            instPermissions={record.permission}
          >
            <Button
              type="link"
              size="small"
              disabled={executing}
              onClick={() => handleCopy(record)}
            >
              {t('Collection.table.copy')}
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
    const nextTaskId = String(record.id);
    const currentTaskId = searchParams.get('taskId');

    setCurrentTask(record);
    setDetailVisible(true);

    if (currentTaskId === nextTaskId) {
      return;
    }

    isSyncingTaskDetailRef.current = true;
    syncUrlState(
      {
        categoryId: selectedCategoryRef.current.categoryId || 'all',
        pluginId: stateRef.current.selectedPluginId || null,
        taskId: nextTaskId,
      },
      'push'
    );
  };

  const handleCloseDetailDrawer = () => {
    isClosingTaskDetailRef.current = true;
    isSyncingTaskDetailRef.current = false;
    setDetailVisible(false);
    setCurrentTask(null);
    syncUrlState({ taskId: null }, 'replace');
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
    syncUrlState(
      {
        categoryId: selectedCategoryRef.current.categoryId || 'all',
        pluginId,
        taskId: null,
      },
      'replace'
    );
  };

  useEffect(() => {
    if (!categoryList.length) {
      return;
    }

    const taskId = searchParams.get('taskId');

    if (!taskId) {
      isClosingTaskDetailRef.current = false;
      if (isSyncingTaskDetailRef.current) {
        return;
      }
      if (detailVisible) {
        setDetailVisible(false);
        setCurrentTask(null);
      }
      return;
    }

    if (isClosingTaskDetailRef.current) {
      return;
    }

    isSyncingTaskDetailRef.current = false;

    if (currentTask && String(currentTask.id) === taskId && detailVisible) {
      return;
    }

    openTaskDetailById(taskId);
  }, [categoryList.length, currentTask, detailVisible, openTaskDetailById, searchParams]);

  const PluginCard: React.FC<PluginCardProps> = ({ tab }) => {
    const isActive = selectedPluginId === tab.id;
    const tags = tab.tag || [];
    const description = tab.desc || '';
    const iconSrc = getCollectionIconSrc(tab);

    const taskStats = taskStatus[tab.model_id || tab.id] || {
      running: 0,
      success: 0,
      failed: 0,
    };

    const statusItems = [
      {
        dotClass: 'bg-blue-500',
        label: t('Collection.statusLabel.running'),
        value: taskStats.running,
      },
      {
        dotClass: 'bg-green-500',
        label: t('Collection.statusLabel.syncSuccess'),
        value: taskStats.success,
      },
      {
        dotClass: 'bg-rose-500',
        label: t('Collection.statusLabel.syncFailed'),
        value: taskStats.failed,
      },
    ];

    return (
      <div
        key={tab.id}
        role="button"
        tabIndex={0}
        className={`group relative w-full shrink-0 cursor-pointer overflow-hidden rounded-2xl border transition-all duration-200 ${
          isActive
            ? 'border-blue-300 bg-linear-to-br from-blue-50 via-white to-sky-50 shadow-[0_14px_28px_rgba(59,130,246,0.14)]'
            : 'border-slate-200 bg-white hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-[0_12px_24px_rgba(15,23,42,0.08)]'
        } p-3 text-left`}
        onClick={() => handlePluginCardClick(tab.id)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            handlePluginCardClick(tab.id);
          }
        }}
      >
        <div
          className={`absolute inset-x-0 top-0 h-1 transition-opacity ${isActive ? 'bg-linear-to-r from-blue-500 via-sky-400 to-cyan-300 opacity-100' : 'bg-linear-to-r from-slate-200 via-slate-100 to-white opacity-0 group-hover:opacity-100'}`}
        />

        <div className="flex items-start gap-2.5">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border shadow-sm transition-colors ${
              isActive
                ? 'border-blue-100 bg-blue-50'
                : 'border-slate-200 bg-slate-50 group-hover:border-blue-100 group-hover:bg-blue-50'
            }`}
          >
            <Image
              src={iconSrc}
              alt={tab.name}
              width={24}
              height={24}
              className={`${isActive ? 'opacity-100' : 'opacity-80 group-hover:opacity-100'}`}
            />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div
                  className={`text-sm font-semibold leading-5 tracking-[0.01em] wrap-break-word ${isActive ? 'text-blue-700' : 'text-slate-900'}`}
                >
                  {tab.name}
                </div>
                <ExpandableText text={description} collapsedLines={2} />
              </div>
              <div
                className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ${isActive ? 'bg-blue-500 shadow-[0_0_0_4px_rgba(59,130,246,0.12)]' : 'bg-slate-200 group-hover:bg-blue-300'}`}
              />
            </div>

            {tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-[11px] leading-4 text-slate-500">
                {tags.map((tag: string) => (
                  <span
                    key={tag}
                    className={`inline-flex items-center wrap-break-word ${isActive ? 'text-blue-700/85' : 'text-slate-500'}`}
                  >
                    <span
                      className={`mr-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${isActive ? 'bg-blue-300' : 'bg-slate-300'}`}
                    />
                    <span className="break-keep">{tag}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        <Tooltip
          placement="left"
          title={
            <div className="flex flex-col gap-1.5">
              {statusItems.map(({ dotClass, value, label }) => (
                <div
                  key={label}
                  className="flex items-center gap-2 text-xs text-white/95"
                >
                  <div
                    className={`h-2 w-2 shrink-0 rounded-full ${dotClass}`}
                  />
                  <span>
                    {label}：{value}
                  </span>
                </div>
              ))}
            </div>
          }
        >
          <div
            className="mt-3 border-t pt-2"
            style={{ borderColor: 'var(--color-border-2)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center">
              {statusItems.map(({ dotClass, value, label }, index) => (
                <div
                  key={label}
                  className={`flex flex-1 items-center justify-center ${index < statusItems.length - 1 ? 'border-r border-slate-200/70' : ''}`}
                >
                  <div
                    className={`flex min-w-10.5 items-center justify-center gap-1.5 rounded-lg px-1.5 py-0.5 transition-colors ${isActive ? 'hover:bg-blue-50/80' : 'hover:bg-slate-100/80'}`}
                    aria-label={`${label}：${value}`}
                  >
                    <div
                      className={`h-2 w-2 shrink-0 rounded-full ${dotClass} ring-2 ring-white shadow-sm`}
                    />
                    <span className="text-sm font-semibold leading-none tabular-nums text-slate-800">
                      {value}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Tooltip>
      </div>
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

      <div className="flex min-h-0 flex-1 overflow-hidden pt-4">
        <div className="flex min-h-0 w-64 shrink-0 flex-col self-stretch">
          {categoryLoading ? (
            <div className="flex items-center justify-center py-4">
              <Spin size="small" />
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-auto px-2 py-1 space-y-3">
              {selectedCategoryRef.current.category?.tabItems?.map((tab) => (
                <PluginCard key={tab.id} tab={tab} />
              ))}
            </div>
          )}
        </div>

        <div
          className="w-px shrink-0 mr-2"
          style={{ backgroundColor: 'var(--color-border-2)' }}
        ></div>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded border border-gray-200 bg-white shadow-sm">
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
                      item.key !== 'action' && 'dataIndex' in item,
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
                : t('Collection.viewDoc')}
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
        onClose={handleCloseDetailDrawer}
        open={detailVisible}
        footer={
          <div className="flex justify-start">
            <Button onClick={handleCloseDetailDrawer}>
              {t('common.close')}
            </Button>
          </div>
        }
      >
        {detailVisible && currentTask && (
          <TaskDetail
            task={currentTask}
            modelId={selectedCategoryRef.current.categoryId}
            onClose={handleCloseDetailDrawer}
            onSuccess={fetchData}
          />
        )}
      </Drawer>
    </div>
  );
};

export default ProfessionalCollection;
