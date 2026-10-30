'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import dayjs from 'dayjs';
import styles from './index.module.scss';
import K8sTask from './components/k8s/k8sGuidedTask';
import VMTask from './components/vmTask';
import WinSphereTask from './components/winsphereTask';
import SNMPTask from './components/snmpTask';
import SQLTask from './components/sqlTask';
import InfluxdbTask from './components/influxdbTask';
import PlatformApiTask from './components/platformApiTask';
import CloudTask from './components/cloudTask';
import HostTask from './components/hostTask';
import IPMITask from './components/ipmiTask';
import RedfishTask from './components/redfishTask';
import ConfigFileTask from './components/configFileTask';
import NetworkConfigFileTask from './components/networkConfigFileTask';
import SslCerTask from './components/sslCerTask';
import IpTask from './components/ipTask';
import PCTask from './components/pcTask';
import CustomScriptTask from './components/customScriptTask';
import PluginCatalogView from './components/pluginCatalogView';
import TaskDetail from './components/taskDetail';
import NodeMgmtSyncDetail from './components/nodeMgmtSyncDetail';
import CollectionStats from './components/collectionStats';
import ReconcileDrawer from './components/reconcileDrawer';
import {
  findPluginCategory,
  resolveCollectPlugin,
} from './pluginCatalog';
import {
  getCredentialDescriptor,
  type CredentialFormKind,
} from './components/credentialDescriptors';
import MarkdownRenderer from '@/components/markdown';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import ToolbarSplitShell from '@/components/toolbar-split-shell';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import { useCollectApi } from '@/app/cmdb/api';
import type { TableColumnType, TablePaginationConfig } from 'antd';
import type { ColumnItem } from '@/app/cmdb/types/assetManage';
import type { ColumnType } from 'antd/es/table';
import type { FilterValue } from 'antd/es/table/interface';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { Alert, Button, Drawer, Input, Modal, Segmented, Spin, Tag, Tooltip, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useLocale } from '@/context/locale';
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
import { usePathname, useSearchParams } from 'next/navigation';
import { useScreenAwareRouter } from '@/console-layout';
import { createCollectionListRequest } from './collectionListRequest';
import { formatCollectReportTime } from './formatCollectReportTime';

type ExtendedColumnItem = ColumnType<CollectTask> & {
  key: string;
  dataIndex?: string;
};

interface TaskFormProps {
  onClose: () => void;
  onSuccess: () => Promise<void>;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId: number | null;
}

const CREDENTIAL_TASK_TYPES = new Set([
  'cloud',
  'host',
  'db',
  'middleware',
  'snmp',
  'protocol',
]);

const CREDENTIAL_TASK_COMPONENTS: Partial<Record<
  CredentialFormKind,
  React.ComponentType<TaskFormProps>
>> = {
  ssh: HostTask,
  sql: SQLTask,
  snmp: SNMPTask,
  influxdb: InfluxdbTask,
  cloud: CloudTask,
  platform_api: PlatformApiTask,
  redfish: RedfishTask,
  winrm: PCTask,
  macos_ssh: PCTask,
};

const getCollectToolProtocol = (pluginId?: string | null) => {
  const normalizedPluginId = (pluginId || '').toLowerCase();
  if (normalizedPluginId === 'physcial_server_ipmi') {
    return 'ipmi';
  }
  if (normalizedPluginId === 'network') {
    return 'snmp';
  }
  return null;
};

const ArrowLeftIcon = ArrowLeftOutlined as React.ComponentType<{ className?: string }>;

type CollectionTaskScope = 'catalog' | 'plugin' | 'all';

const ProfessionalCollection: React.FC = () => {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const collectApi = useCollectApi();
  const router = useScreenAwareRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const editingId = useAssetManageStore((state) => state.editingId);
  const setEditingId = useAssetManageStore((state) => state.setEditingId);
  const setCopyTaskData = useAssetManageStore((state) => state.setCopyTaskData);
  const syncStatusConfig = React.useMemo(() => getExecStatusConfig(t), [t]);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [categoryList, setCategoryList] = useState<TreeNode[]>([]);
  const [detailVisible, setDetailVisible] = useState(false);
  const [nodeMgmtSyncVisible, setNodeMgmtSyncVisible] = useState(false);
  const [reconcileVisible, setReconcileVisible] = useState(false);
  const [currentTask, setCurrentTask] = useState<CollectTask | null>(null);
  const [selectedPluginId, setSelectedPluginId] = useState<string>('');
  const [taskScope, setTaskScope] = useState<CollectionTaskScope>('catalog');
  const [pluginKeyword, setPluginKeyword] = useState('');
  const [formPlugin, setFormPlugin] = useState<TreeNode | null>(null);
  const [formCategory, setFormCategory] = useState<TreeNode | null>(null);
  const taskScopeRef = useRef<CollectionTaskScope>('catalog');
  const categoryListRef = useRef<TreeNode[]>([]);
  const openPluginTasksRef = useRef<(pluginId: string) => void>(() => {});
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
  const [listRequest] = useState(createCollectionListRequest);
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
  const [currentExecStatusUI, setCurrentExecStatusUI] = useState<ExecStatusType | undefined>(undefined);
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
      view?: 'tasks' | null;
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
      if (next.view !== undefined) {
        if (next.view) {
          params.set('view', next.view);
        } else {
          params.delete('view');
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
        view?: 'tasks' | null;
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

  categoryListRef.current = categoryList;
  const currentPlugin = React.useMemo(() => {
    return findPluginCategory(categoryList, selectedPluginId)?.tabItems?.find(
      (item) => item.id === selectedPluginId,
    );
  }, [categoryList, selectedPluginId]);
  const taskDrawerPlugin = formPlugin || currentPlugin;
  const taskDrawerWidth =
    (taskDrawerPlugin?.task_type || taskDrawerPlugin?.type) === 'k8s' ? 740 : 700;
  const docDrawerNested = taskDocDrawerVisible && drawerVisible;
  const docDrawerWidth = docDrawerNested
    ? `min(600px, calc(100vw - ${taskDrawerWidth}px - 24px))`
    : 600;

  const getParams = (pluginId?: string) => {
    const currentPluginId =
      pluginId !== undefined ? pluginId : stateRef.current.selectedPluginId;
    const pluginCategory = currentPluginId
      ? findPluginCategory(categoryListRef.current, currentPluginId)
      : undefined;
    const plugin = pluginCategory?.tabItems?.find(
      (item) => item.id === currentPluginId,
    );
    const listParams = {
      page: stateRef.current.pagination.current,
      page_size: stateRef.current.pagination.pageSize,
      name: stateRef.current.searchText,
      ...(stateRef.current.currentExecStatus !== undefined && {
        exec_status: stateRef.current.currentExecStatus,
      }),
    };
    if (!plugin) {
      return listParams;
    }

    return {
      ...listParams,
      model_id: plugin.model_id || currentPluginId,
      ...(plugin.type && { driver_type: plugin.type }),
      ...(plugin.id === 'physcial_server_ipmi' && {
        collection_protocol: 'ipmi',
      }),
      ...(plugin.id === 'physcial_server_redfish' && {
        collection_protocol: 'redfish',
      }),
      ...(plugin.task_type === 'custom_script' && plugin.custom_plugin_pk
        ? { custom_plugin_pk: plugin.custom_plugin_pk }
        : {}),
    };
  };

  const fetchData = async (showLoading = true, pluginId?: string) => {
    const requestId = listRequest.begin();
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
      listRequest.commitSuccess(requestId, data, (view) => {
        setTableData(view.items);
        tableCountRef.current = view.listCount;
        setPaginationUI((prev) => ({
          ...prev,
          total: view.total,
        }));
      });
    } catch (error) {
      console.error('Failed to fetch table data:', error);
    } finally {
      listRequest.commitSettled(requestId, () => {
        if (showLoading) {
          setTableLoading(false);
        }
        if (taskScopeRef.current === 'catalog') {
          return;
        }
        resetTimer(pluginId);
      });
    }
  };

  const resetTimer = (pluginId?: string) => {
    const currentPluginId =
      pluginId !== undefined ? pluginId : stateRef.current.selectedPluginId;
    listRequest.resetTimer(() => fetchData(false, currentPluginId));
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
        name: t('all'),
        tabItems: categories.flatMap((node: TreeNode) => node.tabItems || []),
      };

      const nextCategories = [allCategory, ...categories];
      setCategoryList(nextCategories);
      categoryListRef.current = nextCategories;
      if (!data.length) return;

      const urlPluginId = searchParams.get('plugin') || '';
      const pluginCategory = findPluginCategory(nextCategories, urlPluginId);
      if (pluginCategory && urlPluginId) {
        selectedCategoryRef.current = {
          categoryId: pluginCategory.id,
          category: pluginCategory,
        };
      } else {
        selectedCategoryRef.current = {
          categoryId: allCategory.id,
          category: allCategory,
        };
      }

      const scope = urlPluginId && pluginCategory
        ? 'plugin'
        : searchParams.get('view') === 'tasks'
          ? 'all'
          : 'catalog';
      taskScopeRef.current = scope;
      if (scope === 'plugin') {
        setSelectedPluginId(urlPluginId);
        stateRef.current.selectedPluginId = urlPluginId;
        setTaskScope('plugin');
        await fetchData(true, urlPluginId);
      } else if (scope === 'all') {
        setSelectedPluginId('');
        stateRef.current.selectedPluginId = '';
        setTaskScope('all');
        await fetchData(true, '');
      } else {
        setSelectedPluginId('');
        stateRef.current.selectedPluginId = '';
        setTaskScope('catalog');
        setTableData([]);
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
    setPluginDoc('');
    if (docDrawerVisible || taskDocDrawerVisible) {
      const pluginId = stateRef.current.selectedPluginId;
      if (pluginId) {
        fetchPluginDoc(pluginId);
      }
    }

    statusTimerRef.current = setInterval(() => {
      fetchTaskStatus();
    }, 30 * 1000);

    return () => {
      listRequest.unmount();
      if (statusTimerRef.current) {
        clearInterval(statusTimerRef.current);
        statusTimerRef.current = null;
      }
    };
  }, [locale]);

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
    setCurrentExecStatusUI(newExecStatus);
    setPaginationUI((prev) => ({
      ...prev,
      current: currentPage,
      pageSize,
    }));

    fetchData();
  };

  const resetTaskListQuery = () => {
    setSearchTextUI('');
    stateRef.current.searchText = '';
    stateRef.current.currentExecStatus = undefined;
    setCurrentExecStatusUI(undefined);
    stateRef.current.pagination.current = 1;
    setPaginationUI((prev) => ({ ...prev, current: 1 }));
    setPluginDoc('');
    setDocLoading(false);
  };

  const openTaskForm = (plugin: TreeNode | undefined) => {
    const category = plugin
      ? findPluginCategory(categoryListRef.current, plugin.id)
      : undefined;
    if (!plugin || !category) {
      message.warning(t('Collection.catalog.pluginMissing'));
      return;
    }
    setFormPlugin(plugin);
    setFormCategory(category);
    setDrawerVisible(true);
  };

  const handleCreate = () => {
    setEditingId(null);
    openTaskForm(currentPlugin);
  };

  const fetchPluginDoc = async (pluginId: string) => {
    try {
      setDocLoading(true);
      const plugin = findPluginCategory(categoryListRef.current, pluginId)?.tabItems?.find(
        (item) => item.id === pluginId,
      );
      if (plugin?.task_type === 'custom_script') {
        const data = await collectApi.getCollectModelDoc('custom_script');
        setPluginDoc(data || '');
        return;
      }
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
    openTaskForm(resolveCollectPlugin(categoryListRef.current, record) || currentPlugin);
  };


  // 复制任务
  const handleCopy = async (record: CollectTask) => {
    try {
      const data = await collectApi.getCollectDetail(record.id.toString());
      setCopyTaskData(data);
      setEditingId(null);
      openTaskForm(resolveCollectPlugin(categoryListRef.current, record) || currentPlugin);
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
      okButtonProps: { danger: true },
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
        message.success(
          t(
            record.model_id === 'pc'
              ? 'Collection.PCTask.syncLatestSuccess'
              : 'Collection.executeSuccess'
          )
        );
        fetchData();
      } catch (error) {
        console.error('Failed to execute task:', error);
      } finally {
        setExecutingTaskIds((prev) => prev.filter((id) => id !== record.id));
      }
    },
    [executingTaskIds]
  );

  const handleGoToCollectTool = useCallback(
    (record: CollectTask) => {
      const plugin = resolveCollectPlugin(categoryListRef.current, record);
      const protocol = getCollectToolProtocol(plugin?.id);
      if (!protocol || !plugin) {
        return;
      }
      const category = findPluginCategory(categoryListRef.current, plugin.id);
      router.push(
        `/cmdb/assetManage/autoDiscovery/featureLibrary/collectionTool?category=${category?.id || 'all'}&plugin=${plugin.id}&protocol=${protocol}&sourceTaskId=${record.id}`
      );
    },
    [router]
  );

  const closeDrawer = () => {
    setEditingId(null);// 编辑任务数据置空
    setCopyTaskData(null); // 复制任务数据置空
    setFormPlugin(null);
    setFormCategory(null);
    setDrawerVisible(false);
    setTaskDocDrawerVisible(false);
  };

  const getTaskContent = () => {
    if (!formCategory || !formPlugin) return null;

    const taskProps = {
      onClose: closeDrawer,
      onSuccess: fetchData,
      selectedNode: formCategory,
      modelItem: formPlugin as ModelItem,
      editId: editingId,
    };

    if (formPlugin.model_id === 'pc') {
      return <PCTask {...taskProps} />;
    }

    if (formPlugin.model_id === 'winsphere') {
      return <WinSphereTask {...taskProps} />;
    }

    if (formPlugin.id === 'physcial_server_ipmi') {
      return <IPMITask {...taskProps} />;
    }

    if (formPlugin.id === 'physcial_server_redfish') {
      return <RedfishTask {...taskProps} />;
    }

    if (formPlugin.model_id === 'network_config_file') {
      return <NetworkConfigFileTask {...taskProps} />;
    }

    if (formPlugin.model_id === 'ssl_cer') {
      return <SslCerTask {...taskProps} />;
    }

    const taskTypeKey = formPlugin.task_type || formPlugin.type || formCategory.id;
    if (formPlugin.model_id === 'vmware_vc' || taskTypeKey === 'vm') {
      return <VMTask {...taskProps} />;
    }

    if (formPlugin.model_id === 'config_file') {
      return <ConfigFileTask {...taskProps} />;
    }

    if (formPlugin.task_type === 'custom_script') {
      return <CustomScriptTask {...taskProps} />;
    }

    const credentialDescriptor = getCredentialDescriptor(formPlugin);
    if (credentialDescriptor) {
      const CredentialTask = CREDENTIAL_TASK_COMPONENTS[
        credentialDescriptor.formKind
      ];
      if (CredentialTask) {
        return <CredentialTask {...taskProps} />;
      }
    }

    if (CREDENTIAL_TASK_TYPES.has(taskTypeKey)) {
      return (
        <Alert
          type="warning"
          showIcon
          message={t('Collection.credentialHelp.unsupportedTitle')}
          description={t('Collection.credentialHelp.unsupportedDescription')}
        />
      );
    }

    const taskMap: Record<string, React.ComponentType<TaskFormProps>> = {
      k8s: K8sTask,
      vm: VMTask,
      config_file: ConfigFileTask,
      ip: IpTask,
    };
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
        <div className="flex gap-3 whitespace-nowrap">
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
              {record.model_id === 'pc'
                ? t(
                  loadingExec
                    ? 'Collection.PCTask.syncingLatestResult'
                    : 'Collection.PCTask.syncLatestResult'
                )
                : t(
                  loadingExec
                    ? 'Collection.table.syncing'
                    : 'Collection.table.sync'
                )}
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
        title: t('Collection.table.pluginName'),
        dataIndex: 'model_id',
        key: 'plugin_name',
        width: 180,
        render: (_value: string, record: CollectTask) => {
          const plugin = resolveCollectPlugin(categoryList, record);
          const label = plugin?.name || record.model_id || '--';
          if (!plugin) {
            return <span>{label}</span>;
          }
          return (
            <Button
              type="link"
              size="small"
              className="h-auto max-w-full px-0"
              onClick={() => openPluginTasksRef.current(plugin.id)}
            >
              <span className="block max-w-[148px] truncate">{label}</span>
            </Button>
          );
        },
      },
      {
        title: t('Collection.table.syncStatus'),
        dataIndex: 'exec_status',
        key: 'exec_status',
        width: 160,
        filters: statusFilters,
        filterMultiple: false,
        filteredValue: currentExecStatusUI !== undefined ? [currentExecStatusUI] : null,
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
          const collectToolProtocol = getCollectToolProtocol(
            resolveCollectPlugin(categoryList, record)?.id,
          );
          const canGoToCollectTool =
            record.exec_status === EXEC_STATUS.ERROR && Boolean(collectToolProtocol);

          const collectToolLink = canGoToCollectTool ? (
            <Button
              type="link"
              danger
              size="small"
              onClick={() => handleGoToCollectTool(record)}
              className="h-auto p-0"
            >
              {t('CollectTool.goToCollectTool')}
            </Button>
          ) : null;

          if (record.exec_status === EXEC_STATUS.ERROR && digest.message) {
            return (
              <div className="flex flex-col items-start gap-1">
                <Tooltip title={digest.message}>
                  <div className={`${styles.ellipsis2Lines} text-gray-500`}>
                    {digest.message}
                  </div>
                </Tooltip>
                {collectToolLink}
              </div>
            );
          }

          const errorTotal =
            (digest.add_error || 0) +
            (digest.delete_error || 0) +
            (digest.update_error || 0);

          return Object.keys(digest).length > 0 ? (
            <div className="flex flex-col items-start gap-1">
              <div className="flex flex-wrap gap-2">
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
              {collectToolLink}
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
            <span>{lastTime ? formatCollectReportTime(lastTime) : '--'}</span>
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
        width: 320,
        render: (_, record) => actionRender(record),
      },
    ],
    [t, actionRender, categoryList, handleGoToCollectTool, currentExecStatusUI]
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
  }, [getColumns]);

  const handlePluginCardClick = useCallback(
    (pluginId: string) => {
      const parent = findPluginCategory(categoryListRef.current, pluginId);
      if (parent) {
        selectedCategoryRef.current = {
          categoryId: parent.id,
          category: parent,
        };
      }
      setSelectedPluginId(pluginId);
      stateRef.current.selectedPluginId = pluginId;
      taskScopeRef.current = 'plugin';
      setTaskScope('plugin');

      listRequest.clearTimer();
      resetTaskListQuery();

      fetchData(true, pluginId);
      syncUrlState(
        {
          categoryId: parent?.id || 'all',
          pluginId,
          view: null,
          taskId: null,
        },
        'replace',
      );
    },
    [fetchData, syncUrlState],
  );
  openPluginTasksRef.current = handlePluginCardClick;

  const showCatalog = () => {
    taskScopeRef.current = 'catalog';
    stateRef.current.selectedPluginId = '';
    stateRef.current.currentExecStatus = undefined;
    setCurrentExecStatusUI(undefined);
    setTaskScope('catalog');
    setSelectedPluginId('');
    listRequest.clearTimer();
    setTableData([]);
    syncUrlState(
      {
        categoryId: null,
        pluginId: null,
        view: null,
        taskId: null,
      },
      'replace',
    );
  };

  const showAllTasks = useCallback(
    (targetStatus?: ExecStatusType) => {
      const allCategory = categoryListRef.current.find((category) => category.id === 'all');
      selectedCategoryRef.current = {
        categoryId: 'all',
        category: allCategory,
      };
      taskScopeRef.current = 'all';
      stateRef.current.selectedPluginId = '';
      setTaskScope('all');
      setSelectedPluginId('');
      listRequest.clearTimer();

      setSearchTextUI('');
      stateRef.current.searchText = '';
      stateRef.current.currentExecStatus = targetStatus;
      setCurrentExecStatusUI(targetStatus);
      stateRef.current.pagination.current = 1;
      setPaginationUI((prev) => ({ ...prev, current: 1 }));
      setPluginDoc('');
      setDocLoading(false);

      fetchData(true, '');
      syncUrlState(
        {
          categoryId: 'all',
          pluginId: null,
          view: 'tasks',
          taskId: null,
        },
        'replace',
      );
    },
    [fetchData, listRequest, syncUrlState],
  );

  const handleStatCardClick = useCallback(
    (key: string) => {
      let targetStatus: ExecStatusType | undefined = undefined;
      if (key === 'normal') {
        targetStatus = EXEC_STATUS.SUCCESS;
      } else if (key === 'error') {
        targetStatus = EXEC_STATUS.ERROR;
      } else if (key === 'partial') {
        targetStatus = EXEC_STATUS.PARTIAL_SUCCESS;
      }

      if (
        taskScopeRef.current === 'all' &&
        stateRef.current.currentExecStatus === targetStatus &&
        targetStatus !== undefined
      ) {
        targetStatus = undefined;
      }

      showAllTasks(targetStatus);
    },
    [showAllTasks],
  );

  const activeStatKey = React.useMemo(() => {
    if (taskScope !== 'all') return null;
    if (currentExecStatusUI === EXEC_STATUS.SUCCESS) return 'normal';
    if (currentExecStatusUI === EXEC_STATUS.ERROR) return 'error';
    if (currentExecStatusUI === EXEC_STATUS.PARTIAL_SUCCESS) return 'partial';
    if (currentExecStatusUI === undefined) return 'total';
    return null;
  }, [taskScope, currentExecStatusUI]);

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

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <CollectionStats
        activeKey={activeStatKey}
        onSelectStat={handleStatCardClick}
      />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-2 pt-2">
        <ToolbarSplitShell
          className="!mb-3 shrink-0"
          leading={(
            <div
              onClick={(event) => {
                if (taskScope !== 'plugin') return;
                const item = (event.target as HTMLElement).closest('.ant-segmented-item');
                if (item?.classList.contains('ant-segmented-item-selected')) {
                  showCatalog();
                }
              }}
            >
              <Segmented
                value={taskScope === 'all' ? 'all' : 'catalog'}
                onChange={(value) => {
                  if (value === 'all') {
                    showAllTasks();
                    return;
                  }
                  showCatalog();
                }}
                options={[
                  { label: t('Collection.catalog.pluginOverview'), value: 'catalog' },
                  { label: t('Collection.catalog.allTasks'), value: 'all' },
                ]}
              />
            </div>
          )}
          trailing={(
            <>
              <Input.Search
                allowClear
                enterButton
                className="!w-80"
                placeholder={
                  taskScope === 'catalog'
                    ? t('Collection.catalog.searchPlaceholder')
                    : t('Collection.inputTaskPlaceholder')
                }
                value={taskScope === 'catalog' ? pluginKeyword : searchTextUI}
                onChange={(event) => {
                  const value = event.target.value;
                  if (taskScope === 'catalog') {
                    setPluginKeyword(value);
                    return;
                  }
                  setSearchTextUI(value);
                  if (!value) {
                    handleSearch('');
                  }
                }}
                onSearch={(value) => {
                  if (taskScope === 'catalog') {
                    setPluginKeyword(value);
                    return;
                  }
                  handleSearch(value);
                }}
              />
              <Button type="link" onClick={() => setNodeMgmtSyncVisible(true)}>
                {t('Collection.nodeMgmtSync.entry')}
              </Button>
              {taskScope === 'plugin' ? (
                <Button onClick={() => setReconcileVisible(true)}>
                  {t('Collection.reconcileOpen')}
                </Button>
              ) : null}
              {taskScope === 'plugin' ? (
                <PermissionWrapper requiredPermissions={['Add']}>
                  <Button type="primary" onClick={handleCreate}>
                    {t('Collection.addTaskTitle')}
                  </Button>
                </PermissionWrapper>
              ) : null}
            </>
          )}
        />

        {taskScope === 'catalog' ? (
          <div className="min-h-0 flex-1 overflow-auto pb-3">
            {categoryLoading && categoryList.length === 0 ? (
              <CardGridSkeleton
                count={6}
                className="grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5"
              />
            ) : (
              <PluginCatalogView
                categories={categoryList}
                taskStatus={taskStatus}
                keyword={pluginKeyword}
                onSelectPlugin={handlePluginCardClick}
              />
            )}
          </div>
        ) : (
          <div className="flex min-h-[360px] min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_2px_12px_rgba(0,0,0,0.03),0_12px_24px_rgba(0,0,0,0.02)]">
            <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/50 px-5 py-3">
              {taskScope === 'plugin' ? (
                <Button
                  type="link"
                  size="small"
                  className="px-0"
                  icon={<ArrowLeftIcon />}
                  onClick={showCatalog}
                >
                  {t('Collection.catalog.backToPlugins')}
                </Button>
              ) : null}
              <span className="text-[13px] font-semibold text-[var(--color-text-1)]">
                {taskScope === 'plugin'
                  ? (currentPlugin?.name || '')
                  : t('Collection.catalog.allTasks')}
              </span>
              {taskScope === 'all' && currentExecStatusUI !== undefined && (
                <Tag
                  closable
                  color={
                    currentExecStatusUI === EXEC_STATUS.ERROR
                      ? 'error'
                      : currentExecStatusUI === EXEC_STATUS.SUCCESS
                        ? 'success'
                        : 'warning'
                  }
                  onClose={() => showAllTasks(undefined)}
                >
                  {syncStatusConfig[currentExecStatusUI]?.text || ''}
                </Tag>
              )}
              {taskScope === 'plugin' && currentPlugin?.desc ? (
                <span className="min-w-0 flex-1 truncate text-xs text-[var(--color-text-3)]">
                  {currentPlugin.desc}
                </span>
              ) : null}
              {taskScope === 'plugin' ? (
                <Button type="link" size="small" onClick={handleViewDoc}>
                  {t('Collection.viewDoc')}
                </Button>
              ) : null}
            </div>

            <div className="min-h-0 flex-1 overflow-hidden px-4 pb-1 pt-3">
              <div className={styles.collectionTaskTable}>
                <CustomTable
                  loading={tableLoading}
                  key={taskScope === 'plugin' ? selectedPluginId : 'all-tasks'}
                  size="middle"
                  rowKey="id"
                  columns={currentColumns}
                  dataSource={tableData}
                  onSelectFields={onSelectFields}
                  onChange={handleTableChange}
                  pagination={{
                    ...paginationUI,
                    showSizeChanger: true,
                    showTotal: (total) => t('Collection.taskDetail.paginationTotal', '', { total }),
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
        )}
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
                const docPluginId = formPlugin?.id || selectedPluginId;
                if (!taskDocDrawerVisible && docPluginId && !pluginDoc) {
                  fetchPluginDoc(docPluginId);
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
        width={taskDrawerWidth}
        onClose={closeDrawer}
        open={drawerVisible}
        maskClosable={false}
        keyboard={false}
        getContainer={false}
        className={styles.collectionTaskDrawer}
        rootClassName={styles.collectionTaskDrawer}
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
        width={docDrawerWidth}
        onClose={() => {
          setTaskDocDrawerVisible(false);
          setDocDrawerVisible(false);
        }}
        open={docDrawerVisible || docDrawerNested}
        getContainer={docDrawerNested ? false : undefined}
        styles={{
          wrapper: {
            boxShadow:
              docDrawerNested ? 'none' : undefined,
            borderRight:
              docDrawerNested
                ? '1px solid var(--color-border-1)'
                : undefined,
          },
        }}
        mask={docDrawerNested ? false : true}
        rootStyle={
          docDrawerNested
            ? {
              position: 'absolute',
              left: 'auto',
              right: `${taskDrawerWidth}px`,
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
        title={t('Collection.nodeMgmtSync.title')}
        placement="right"
        width={840}
        onClose={() => setNodeMgmtSyncVisible(false)}
        open={nodeMgmtSyncVisible}
        footer={
          <div className="flex justify-start">
            <Button onClick={() => setNodeMgmtSyncVisible(false)}>
              {t('common.close')}
            </Button>
          </div>
        }
      >
        <NodeMgmtSyncDetail open={nodeMgmtSyncVisible} />
      </Drawer>
      <ReconcileDrawer
        open={reconcileVisible}
        modelId={currentPlugin?.model_id || selectedPluginId}
        modelName={currentPlugin?.name || ''}
        groups={categoryList.filter((node) => node.id !== 'all').map((node) => ({
          id: node.id,
          name: node.name,
          plugins: (node.tabItems || []).filter((plugin) => (
            ['host', 'db', 'middleware', 'protocol', 'snmp', 'other', 'custom_script'].includes(plugin.task_type || '')
            && !(plugin.task_type === 'custom_script' && (plugin.model_id === 'vmware_vc' || plugin.id === 'vmware_vc'))
          )),
        })).filter((group) => group.plugins.length > 0)}
        onClose={() => setReconcileVisible(false)}
      />

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
