'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { KeepAlive } from 'react-activation';
import {
  Button,
  Space,
  Modal,
  message,
  Spin,
  Dropdown,
  TablePaginationConfig,
  Tree,
  Input,
  Empty,
} from 'antd';
import type { MenuProps } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import { useSearchParams, usePathname, useRouter } from 'next/navigation';
import CustomTable from '@/components/custom-table';
import GroupTreeSelector from '@/components/group-tree-select';
import PermissionWrapper from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import { deepClone, getAssetColumns } from '@/app/cmdb/utils/common';
import { useCommon } from '@/app/cmdb/context/common';
import { useAssetDataStore, type FilterItem } from '@/app/cmdb/store';
import { useModelApi, useClassificationApi, useInstanceApi } from '@/app/cmdb/api';
import {
  GroupItem,
  ModelItem,
  ColumnItem,
  UserItem,
  AttrFieldType,
  RelationInstanceRef,
  AssoTypeItem,
  FullInfoGroupItem,
} from '@/app/cmdb/types/assetManage';
import { ExportModalRef } from '@/app/cmdb/types/assetData';
import SearchFilter from './list/searchFilter';
import FilterBar from './list/filterBar';
import ImportInst from './list/importInst';
import FieldModal from './list/fieldModal';
import SelectInstance from './detail/relationships/selectInstance';
import ExportModal from './components/exportModal';
import assetDataStyle from './index.module.scss';

const { confirm } = Modal;

const GROUP_KEY_PREFIX = 'group:';
const COPY_EXCLUDE_FIELDS = ['_id', 'inst_id', 'id', 'created_at', 'updated_at', 'created_by', 'updated_by'];

const buildGroupKey = (classificationId: string) => `${GROUP_KEY_PREFIX}${classificationId}`;
const isGroupKey = (key: string) => key.startsWith(GROUP_KEY_PREFIX);

const parseUrlQueryList = (urlQueryList: string): FilterItem[] | null => {
  if (!urlQueryList) return null;
  try {
    const parsed = JSON.parse(decodeURIComponent(urlQueryList));
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : null;
  } catch {
    console.error('Failed to parse query_list from URL');
    return null;
  }
};

const buildModelGroups = (groupData: GroupItem[], modelList: ModelItem[]): GroupItem[] => {
  const groups = deepClone(groupData).map((item: GroupItem) => ({
    ...item,
    list: [],
    count: 0,
  }));
  modelList.forEach((modelItem: ModelItem) => {
    const target = groups.find((item: GroupItem) => item.classification_id === modelItem.classification_id);
    if (target) {
      target.list.push(modelItem);
      target.count++;
    }
  });
  return groups;
};

const buildTreeData = (
  modelGroup: GroupItem[],
  renderTitle: (name: string, id: string) => React.ReactNode
) => {
  return modelGroup.map((group) => ({
    title: group.classification_name,
    content: group.classification_name,
    key: buildGroupKey(group.classification_id),
    children: group.list.map((item) => ({
      content: item.model_name,
      title: renderTitle(item.model_name, item.model_id),
      key: item.model_id,
    })),
  }));
};

const filterTreeNodes = (nodes: any[], searchText: string, renderTitle: (name: string, id: string) => React.ReactNode): any[] => {
  if (!searchText) return nodes;
  const lowerSearch = searchText.toLowerCase();

  return nodes.reduce((filtered: any[], node) => {
    const matchesSearch = node.content?.toLowerCase().includes(lowerSearch);

    if (node.children) {
      const filteredChildren = filterTreeNodes(node.children, searchText, renderTitle);
      if (filteredChildren.length > 0 || matchesSearch) {
        filtered.push({
          ...node,
          children: filteredChildren.map((child) => ({
            ...child,
            title: renderTitle(child.content, child.key),
          })),
        });
      }
    } else if (matchesSearch) {
      filtered.push(node);
    }
    return filtered;
  }, []);
};

const getAllTreeKeys = (nodes: any[]): string[] => {
  return nodes.reduce((keys: string[], node) => {
    keys.push(node.key);
    if (node.children) keys.push(...getAllTreeKeys(node.children));
    return keys;
  }, []);
};

interface ModelTabs {
  key: string;
  label: string;
  icn: string;
}

interface FieldRef {
  showModal: (config: {
    type: string;
    attrList: FullInfoGroupItem[];
    formInfo: any;
    subTitle: string;
    title: string;
    model_id: string;
    list: Array<any>;
  }) => void;
}

interface ImportRef {
  showModal: (config: {
    subTitle: string;
    title: string;
    model_id: string;
  }) => void;
}

const AssetDataContent = () => {
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const { getModelAssociationTypes, getModelAttrList, getModelAttrGroupsFullInfo } = useModelApi();
  const { getClassificationList } = useClassificationApi();
  const {
    getInstanceProxys,
    searchInstances,
    getModelInstanceCount,
    getInstanceShowFieldDetail,
    setInstanceShowFieldSettings,
    deleteInstance,
    batchDeleteInstances,
  } = useInstanceApi();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const assetModelId: string = searchParams.get('modelId') || '';
  const assetClassificationId: string =
    searchParams.get('classificationId') || '';
  const urlQueryList: string = searchParams.get('query_list') || '';
  const commonContext = useCommon();
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const modelListFromContext = commonContext?.modelList || [];
  const fieldRef = useRef<FieldRef>(null);
  const importRef = useRef<ImportRef>(null);
  const instanceRef = useRef<RelationInstanceRef>(null);
  const exportRef = useRef<ExportModalRef>(null);
  const topRowRef = useRef<HTMLDivElement | null>(null);
  const leftActionsRef = useRef<HTMLDivElement | null>(null);
  const actionSizerRef = useRef<HTMLDivElement | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Array<any>>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [modelGroup, setModelGroup] = useState<GroupItem[]>([]);
  const [originModels, setOriginModels] = useState<ModelItem[]>([]);
  const [groupId, setGroupId] = useState<string>('');
  const [modelId, setModelId] = useState<string>('');
  const [modelList, setModelList] = useState<ModelTabs[]>([]);
  const [propertyListGroups, setPropertyListGroups] = useState<FullInfoGroupItem[]>([]);
  const [propertyList, setPropertyList] = useState<AttrFieldType[]>([]);
  const [displayFieldKeys, setDisplayFieldKeys] = useState<string[]>([]);
  const [columns, setColumns] = useState<ColumnItem[]>([]);
  const [currentColumns, setCurrentColumns] = useState<ColumnItem[]>([]);
  const [assoTypes, setAssoTypes] = useState<AssoTypeItem[]>([]);
  const [queryList, setQueryList] = useState<FilterItem | FilterItem[] | null>(null);
  const [tableData, setTableData] = useState<any[]>([]);
  const [organization, setOrganization] = useState<number[]>([]);
  const [selectedTreeKeys, setSelectedTreeKeys] = useState<string[]>([]);
  const [expandedTreeKeys, setExpandedTreeKeys] = useState<string[]>([]);
  const [proxyOptions, setProxyOptions] = useState<
    { proxy_id: string; proxy_name: string }[]
  >([]);
  const [pagination, setPagination] = useState<TablePaginationConfig>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [treeSearchText, setTreeSearchText] = useState('');
  const [filteredTreeData, setFilteredTreeData] = useState<any[]>([]);
  const [modelInstCount, setModelInstCount] = useState<Record<string, number>>(
    {}
  );
  // 是否折叠操作栏
  const [isActionsCollapsed, setIsActionsCollapsed] = useState(false);
  const urlQueryInitialized = useRef(false);
  const initialDataLoaded = useRef(false);

  // 监听窗口大小变化，更新折叠状态
  useEffect(() => {
    const rowEl = topRowRef.current;
    const leftEl = leftActionsRef.current;
    const sizerEl = actionSizerRef.current;
    if (!rowEl || !leftEl || !sizerEl) return;

    let frameId: number | null = null;
    const updateCollapseState = () => {
      if (!rowEl || !leftEl || !sizerEl) return;
      const rowWidth = rowEl.getBoundingClientRect().width;
      const leftContentWidth = leftEl.scrollWidth;
      const sizerWidth = sizerEl.getBoundingClientRect().width;
      const recoveryBuffer = 30;
      const shouldCollapse = leftContentWidth + sizerWidth > rowWidth + recoveryBuffer;
      setIsActionsCollapsed((prev) => (prev === shouldCollapse ? prev : shouldCollapse));
    };

    // 创建一个观察器，当窗口大小变化时，更新折叠状态
    const observer = new ResizeObserver(() => {
      if (frameId) cancelAnimationFrame(frameId);
      frameId = requestAnimationFrame(updateCollapseState);
    });

    // 监听窗口大小变化
    observer.observe(rowEl);
    observer.observe(leftEl);
    observer.observe(sizerEl);
    updateCollapseState();  // 更新折叠状态

    // 不要忘记清理内存
    return () => {
      if (frameId) cancelAnimationFrame(frameId);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    // 主页中当模型为host时，获取云区域选项test8.7
    if (modelId === 'host') {
      getInstanceProxys()
        .then((data: any[]) => {
          setProxyOptions(data || []);

          // 保存云区域列表到前端store
          useAssetDataStore.getState().setCloudList(data || []);
        })
        .catch(() => {
          setProxyOptions([]);
        });
    }
  }, [modelId]);

  const handleExport = async (
    exportType: 'selected' | 'currentPage' | 'all'
  ) => {
    let title = '';
    let selectedKeys: string[] = [];

    switch (exportType) {
      case 'selected':
        title = `${t('export')}${t('selected')}`;
        selectedKeys = selectedRowKeys;
        break;
      case 'currentPage':
        title = `${t('export')}${t('currentPage')}`;
        selectedKeys = tableData.map((item) => item._id);
        break;
      case 'all':
        title = `${t('export')}${t('all')}`;
        selectedKeys = [];
        break;
    }

    exportRef.current?.showModal({
      title,
      modelId,
      columns,
      displayFieldKeys,
      selectedKeys,
      exportType,
      tableData,
    } as any);
  };

  const showImportModal = () => {
    importRef.current?.showModal({
      title: t('import'),
      subTitle: '',
      model_id: modelId,
    });
  };

  // 添加实例菜单项
  const addInstItems: MenuProps['items'] = [
    {
      key: '1',
      label: (
        <div
          className={assetDataStyle.menuItemClickable}
          onClick={() => showAttrModal('add')}
        >
          {t('common.add')}
        </div>
      ),
    },
    {
      key: '2',
      label: (
        <div className={assetDataStyle.menuItemClickable} onClick={showImportModal}>
          {t('import')}
        </div>
      ),
    },
  ];

  useEffect(() => {
    if (modelListFromContext.length > 0) {
      getModelGroup();
    }
  }, [modelListFromContext]);

  useEffect(() => {
    if (modelId && initialDataLoaded.current) {
      setSelectedTreeKeys([modelId]);
      fetchData();
    }
  }, [pagination?.current, pagination?.pageSize, queryList, organization]);

  useEffect(() => {
    setExpandedTreeKeys(modelGroup.map((item) => buildGroupKey(item.classification_id)));
  }, [modelGroup]);

  const fetchData = async () => {
    setTableLoading(true);
    try {
      const data = await searchInstances(getTableParams());
      setTableData(data.insts);
      setPagination(prev => ({ ...prev, total: data.count }));
    } catch (error) {
      if ((error as { name?: string })?.name === 'CanceledError') return;
    } finally {
      setTableLoading(false);
    }
  };

  const getModelGroup = async () => {
    try {
      setLoading(true);
      const [groupData, assoType, instCount] = await Promise.all([
        getClassificationList(),
        getModelAssociationTypes(),
        getModelInstanceCount(),
      ]);

      const groups = buildModelGroups(groupData, modelListFromContext);
      const defaultGroupId = assetClassificationId || groupData[0].classification_id;
      const filteredModels = modelListFromContext
        .filter((item: ModelItem) => item.classification_id === defaultGroupId)
        .map((item: ModelItem) => ({ key: item.model_id, label: item.model_name, icn: item.icn }));
      const defaultModelId = assetModelId || filteredModels[0].key;

      setModelInstCount(instCount);
      setGroupId(defaultGroupId);
      setModelGroup(groups);
      setOriginModels(modelListFromContext);
      setAssoTypes(assoType);
      setModelList(filteredModels);
      setModelId(defaultModelId);
      setSelectedTreeKeys([defaultModelId]);

      const initialQueryList = parseUrlQueryList(urlQueryList);
      if (initialQueryList) {
        useAssetDataStore.getState().setQueryList(initialQueryList);
      }
      urlQueryInitialized.current = true;

      getInitData(defaultModelId, initialQueryList);
      updateUrl(defaultModelId, defaultGroupId, urlQueryList);
    } catch {
      setLoading(false);
    }
  };

  const updateUrl = (modelId: string, groupId: string, queryList?: string) => {
    const urlParams = new URLSearchParams();
    urlParams.set('modelId', modelId);
    urlParams.set('classificationId', groupId);
    if (queryList) urlParams.set('query_list', queryList);
    router.replace(`/cmdb/assetData?${urlParams.toString()}`);
  };

  const getTableParams = (overrideQueryList?: FilterItem | FilterItem[] | null) => {
    const activeQueryList = overrideQueryList !== undefined ? overrideQueryList : queryList;
    const orgCondition = organization?.length
      ? [{ field: 'organization', type: 'list[]', value: organization }]
      : [];
    const caseSensitive = useAssetDataStore.getState().case_sensitive;

    let finalQueryList: (FilterItem | { field: string; type: string; value: number[] })[] = [];
    if (activeQueryList) {
      finalQueryList = Array.isArray(activeQueryList)
        ? [...activeQueryList, ...orgCondition]
        : [activeQueryList, ...orgCondition];
    } else {
      finalQueryList = orgCondition;
    }

    return {
      query_list: finalQueryList,
      page: pagination.current,
      page_size: pagination.pageSize,
      order: '',
      model_id: modelId,
      role: '',
      case_sensitive: caseSensitive,
    };
  };

  const getInitData = (id: string, overrideQueryList?: FilterItem[] | null) => {
    const tableParams = getTableParams(overrideQueryList);

    getModelAttrGroupsFullInfo(id)
      .then((res) => setPropertyListGroups(res.groups))
      .catch(() => message.error(t('common.getFailed')));

    setLoading(true);
    Promise.all([
      getModelAttrList(id),
      searchInstances({ ...tableParams, model_id: id }),
      getInstanceShowFieldDetail(id),
    ])
      .then(([attrList, instData, displayFields]) => {
        const fieldKeys = displayFields?.show_fields || attrList.map((item: AttrFieldType) => item.attr_id);
        setDisplayFieldKeys(fieldKeys);
        setPropertyList(attrList);
        setTableData(instData.insts);
        setPagination(prev => ({ ...prev, total: instData.count }));
        initialDataLoaded.current = true;
      })
      .finally(() => setLoading(false));
  };

  const onSelectChange = (selectedKeys: any) => {
    setSelectedRowKeys(selectedKeys);
  };

  const rowSelection = {
    selectedRowKeys,
    onChange: onSelectChange,
  };

  const onSelectFields = async (fields: string[]) => {
    setLoading(true);
    try {
      await setInstanceShowFieldSettings(modelId, fields);
      message.success(t('successfulSetted'));
      getInitData(modelId, queryList ? (Array.isArray(queryList) ? queryList : [queryList]) : null);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteWithConfirm = (deleteAction: () => Promise<void>) => {
    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      async onOk() {
        try {
          await deleteAction();
          message.success(t('successfullyDeleted'));
          if (pagination.current && pagination.current > 1 && tableData.length === 1) {
            setPagination(prev => ({ ...prev, current: prev.current! - 1 }));
          }
          setSelectedRowKeys([]);
          fetchData();
        } catch { /* API error handled by interceptor */ }
      },
    });
  };

  const showDeleteConfirm = (row: { _id: string }) => {
    handleDeleteWithConfirm(() => deleteInstance(row._id));
  };

  const batchDeleteConfirm = () => {
    handleDeleteWithConfirm(() => batchDeleteInstances(selectedRowKeys));
  };

  // 导出菜单项
  const exportItems: MenuProps['items'] = [
    {
      key: 'batchExport',
      label: (
        <div
          className={assetDataStyle.menuItemClickable}
          onClick={() => handleExport('selected')}
        >
          {t('selected')}
        </div>
      ),
      disabled: !selectedRowKeys.length,
    },
    {
      key: 'exportCurrentPage',
      label: (
        <div
          className={assetDataStyle.menuItemClickable}
          onClick={() => handleExport('currentPage')}
        >
          {t('currentPage')}
        </div>
      ),
    },
    {
      key: 'exportAll',
      label: (
        <div
          className={assetDataStyle.menuItemClickable}
          onClick={() => handleExport('all')}
        >
          {t('all')}
        </div>
      ),
    },
  ];

  const updateFieldList = async (id?: string) => {
    await fetchData();
    const instCount = await getModelInstanceCount().catch(() => null);
    if (instCount) setModelInstCount(instCount);
    if (id) showInstanceModal({ _id: id });
  };

  const showAttrModal = (type: string, row = {}) => {
    const title = type === 'add' ? t('common.addNew') : t('common.edit');
    fieldRef.current?.showModal({
      title,
      type,
      attrList: propertyListGroups,
      formInfo: row,
      subTitle: '',
      model_id: modelId,
      list: selectedRowKeys,
    });
  };

  const showCopyModal = (record: any) => {
    const copyData = { ...record };
    COPY_EXCLUDE_FIELDS.forEach((field) => delete copyData[field]);

    propertyListGroups
      .flatMap((group) => group.attrs || [])
      .filter((attr) => attr.is_required && attr.is_only && copyData[attr.attr_id])
      .forEach((attr) => { copyData[attr.attr_id] = `${copyData[attr.attr_id]}_copy`; });

    fieldRef.current?.showModal({
      title: t('common.copy'),
      type: 'add',
      attrList: propertyListGroups,
      formInfo: copyData,
      subTitle: '',
      model_id: modelId,
      list: [],
    });
  };

  const handleTableChange = (pagination = {}) => {
    setPagination(pagination);
  };

  const handleSearch = (condition: FilterItem | null) => {
    const { add, remove, update, query_list: currentList } = useAssetDataStore.getState();
    const isClearCondition = !condition || !condition.type;

    if (isClearCondition) {
      if (condition?.field) {
        const index = currentList.findIndex((item) => item.field === condition.field);
        if (index !== -1) remove(index);
      }
      return;
    }

    const existingIndex = currentList.findIndex((item) => item.field === condition.field);
    if (existingIndex !== -1) {
      update(existingIndex, condition);
    } else {
      add(condition);
    }
  };

  const storeQueryList = useAssetDataStore((state) => state.query_list);

  useEffect(() => {
    // 如果查询条件为空，则设置为 null，否则设置为查询条件
    const newQueryList = storeQueryList.length === 0 ? null
      : storeQueryList.length === 1
        ? storeQueryList[0]
        : storeQueryList;
    setQueryList(newQueryList);
  }, [storeQueryList]);

  useEffect(() => {
    if (!urlQueryInitialized.current || !modelId) return;

    const params = new URLSearchParams(searchParams.toString());
    if (storeQueryList.length > 0) {
      params.set('query_list', encodeURIComponent(JSON.stringify(storeQueryList)));
    } else {
      params.delete('query_list');
    }

    const newUrl = `${pathname}?${params.toString()}`;
    const currentUrl = `${pathname}?${searchParams.toString()}`;
    if (newUrl !== currentUrl) {
      router.replace(newUrl, { scroll: false });
    }
  }, [storeQueryList, modelId, pathname, searchParams, router]);

  const handleFilterBarChange = useCallback(() => { }, []);

  const checkDetail = (row = { _id: '', inst_name: '', ip_addr: '' }) => {
    const modelItem = modelList.find((item) => item.key === modelId);
    router.push(
      `/cmdb/assetData/detail/baseInfo?icn=${modelItem?.icn || ''}&model_name=${modelItem?.label || ''
      }&model_id=${modelId}&classification_id=${groupId}&inst_id=${row._id
      }&${row.inst_name ? `inst_name=${row.inst_name}` : `ip_addr=${row.ip_addr}`}`
    );
  };

  const selectOrganization = (value: number | number[] | undefined) => {
    const orgArray = Array.isArray(value) ? value : (value ? [value] : []);
    setOrganization(orgArray);
  };

  const showInstanceModal = (row = { _id: '' }) => {
    instanceRef.current?.showModal({
      title: t('Model.association'),
      model_id: modelId,
      list: [],
      instId: row._id,
    });
  };

  const renderModelTitle = useCallback(
    (modelName: string, modelId: string) => (
      <div className="flex items-center">
        <EllipsisWithTooltip text={modelName} className={assetDataStyle.treeLabel} />
        <span className="ml-1 text-gray-400">({modelInstCount[modelId] || 0})</span>
      </div>
    ),
    [modelInstCount]
  );

  const handleTreeSearch = useCallback(
    (searchText: string) => {
      setTreeSearchText(searchText);
      const treeData = buildTreeData(modelGroup, renderModelTitle);
      const filtered = filterTreeNodes(treeData, searchText, renderModelTitle);
      setFilteredTreeData(filtered);

      const expandedKeys = searchText
        ? getAllTreeKeys(filtered)
        : modelGroup.map((item) => buildGroupKey(item.classification_id));
      setExpandedTreeKeys(expandedKeys);
    },
    [modelGroup, renderModelTitle]
  );

  useEffect(() => {
    setFilteredTreeData(buildTreeData(modelGroup, renderModelTitle));
  }, [modelGroup, renderModelTitle]);

  const onSelectUnified = (selectedKeys: React.Key[]) => {
    useAssetDataStore.getState().clear();
    useAssetDataStore.setState((state) => ({ ...state, searchAttr: '' }));
    urlQueryInitialized.current = true;

    if (!selectedKeys.length) return;
    const key = selectedKeys[0] as string;
    if (key === modelId || isGroupKey(key)) return;

    const targetGroup = modelGroup.find((group) => group.list.some((item) => item.model_id === key));
    if (!targetGroup) return;

    setQueryList(null);
    setSelectedTreeKeys([key]);
    setModelId(key);
    setSelectedRowKeys([]);
    setPagination((prev) => ({ ...prev, current: 1 }));
    setGroupId(targetGroup.classification_id);
    setModelList(targetGroup.list.map((item) => ({ key: item.model_id, label: item.model_name, icn: item.icn })));
    router.push(`/cmdb/assetData?modelId=${key}&classificationId=${targetGroup.classification_id}`);
    getInitData(key, null);
  };

  useEffect(() => {
    if (!propertyList.length) return;

    const attrList = getAssetColumns({ attrList: propertyList, userList, t });
    const actionColumn: ColumnItem = {
      title: t('common.actions'),
      key: 'action',
      dataIndex: 'action',
      width: 280,
      fixed: 'right',
      render: (_: unknown, record: any) => (
        <>
          <Button type="link" className="mr-[10px]" onClick={() => checkDetail(record)}>
            {t('common.detail')}
          </Button>
          <PermissionWrapper requiredPermissions={['Add Associate']} instPermissions={record.permission}>
            <Button type="link" className="mr-[10px]" onClick={() => showInstanceModal(record)}>
              {t('Model.association')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="link" className="mr-[10px]" onClick={() => showCopyModal(record)}>
              {t('common.copy')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit']} instPermissions={record.permission}>
            <Button type="link" className="mr-[10px]" onClick={() => showAttrModal('edit', record)}>
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']} instPermissions={record.permission}>
            <Button type="link" onClick={() => showDeleteConfirm(record)}>
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </>
      ),
    };
    const tableColumns = [...attrList, actionColumn];
    setColumns(tableColumns);

    const orderedColumns = tableColumns
      .filter((col) => displayFieldKeys.includes(col.key as string))
      .sort((a, b) => displayFieldKeys.indexOf(a.key as string) - displayFieldKeys.indexOf(b.key as string));
    setCurrentColumns([...orderedColumns, actionColumn]);
  }, [propertyList, displayFieldKeys]);

  const batchOperateItems: MenuProps['items'] = [
    {
      key: 'batchEdit',
      label: (
        <PermissionWrapper requiredPermissions={['Edit']}>
          <a
            onClick={() => {
              showAttrModal('batchEdit');
            }}
          >
            {t('batchEdit')}
          </a>
        </PermissionWrapper>
      ),
      disabled: !selectedRowKeys.length,
    },
    {
      key: 'batchDelete',
      label: (
        <PermissionWrapper requiredPermissions={['Delete']}>
          <a onClick={batchDeleteConfirm}>{t('common.batchDelete')}</a>
        </PermissionWrapper>
      ),
      disabled: !selectedRowKeys.length,
    },
  ];

  // 添加实例菜单项，添加权限检查
  const addInstItemsWithPermission: MenuProps['items'] = addInstItems.map(
    (item) => {
      if (!item || ('type' in item && item.type === 'divider') || !('label' in item)) {
        return item;
      }
      return {
        ...item,
        label: (
          <PermissionWrapper requiredPermissions={['Add']} fallback={item.label}>
            {item.label}
          </PermissionWrapper>
        ),
      };
    }
  );

  const buildPrefixedItems = (items: MenuProps['items'], prefix: string) =>
    items.map((item, index) => {
      if (!item) return item;
      const baseKey = 'key' in item && item.key ? item.key : `${prefix}-${index}`;
      return {
        ...item,
        key: `${prefix}-${baseKey}`,
      };
    });

  const collapsedMoreItems: MenuProps['items'] = [
    ...buildPrefixedItems(addInstItemsWithPermission, 'add'),
    { type: 'divider', key: 'divider-add-export' },
    ...buildPrefixedItems(exportItems, 'export'),
    { type: 'divider', key: 'divider-export-batch' },
    ...buildPrefixedItems(batchOperateItems, 'batch'),
  ];

  return (
    <Spin spinning={loading} wrapperClassName={assetDataStyle.assetLoading}>
      <div className={assetDataStyle.assetData}>
        {/* 左侧树形选择器 */}
        <div className={`${assetDataStyle.groupSelector}`}>
          <div className={assetDataStyle.treeSearchWrapper}>
            <Input.Search
              placeholder={t('common.search')}
              value={treeSearchText}
              allowClear
              enterButton
              onSearch={handleTreeSearch}
              onChange={(e) => setTreeSearchText(e.target.value)}
            />
          </div>
          <div className={assetDataStyle.treeWrapper}>
            {filteredTreeData.length > 0 ? (
              <Tree
                showLine
                selectedKeys={selectedTreeKeys}
                expandedKeys={expandedTreeKeys}
                onExpand={(keys) => setExpandedTreeKeys(keys as string[])}
                onSelect={onSelectUnified}
                treeData={filteredTreeData}
              />
            ) : (
              <div className="flex justify-center items-center h-full">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('common.noData')}
                />
              </div>
            )}
          </div>
        </div>
        {/* 右侧资产列表 */}
        <div className={assetDataStyle.assetList}>
          <div
            ref={topRowRef}
            className={`flex justify-between ${storeQueryList.length === 0 ? 'mb-4' : ''}`}
          >
            {/* 左侧组织搜索框 */}
            <div ref={leftActionsRef}>
              <Space>
                <GroupTreeSelector
                  style={{
                    width: '200px',
                  }}
                  placeholder={t('common.selectTip')}
                  value={organization}
                  onChange={selectOrganization}
                  filterByRootId={
                    selectedGroup?.id ? Number(selectedGroup.id) : undefined
                  }
                />
                {/* 中间部分 */}
                <SearchFilter
                  key={modelId}
                  proxyOptions={proxyOptions}
                  userList={userList}
                  modelId={modelId}
                  attrList={propertyList.filter(
                    (item) => item.attr_type !== 'organization'
                  )}
                  onSearch={handleSearch}
                  onChange={handleFilterBarChange}
                  onFilterChange={handleFilterBarChange}
                />
              </Space>
            </div>
            {/* 右侧操作按钮 */}
            <Space>
              <div
                className={`${assetDataStyle.actionGroup} ${isActionsCollapsed ? assetDataStyle.actionGroupCollapsed : ''}`}
                aria-hidden={isActionsCollapsed}
              >
                <PermissionWrapper requiredPermissions={['Add']}>
                  <Dropdown menu={{ items: addInstItems }} placement="bottom">
                    <Button type="primary">
                      <Space>
                        {t('common.addNew')}
                        <DownOutlined />
                      </Space>
                    </Button>
                  </Dropdown>
                </PermissionWrapper>
                <Dropdown menu={{ items: exportItems }} placement="bottom">
                  <Button>
                    <Space>
                      {t('export')}
                      <DownOutlined />
                    </Space>
                  </Button>
                </Dropdown>
              </div>
              <Dropdown
                menu={{ items: isActionsCollapsed ? collapsedMoreItems : batchOperateItems }}
                disabled={!isActionsCollapsed && !selectedRowKeys.length}
                placement="bottom"
              >
                <Button>
                  <Space>
                    {t('more')}
                    <DownOutlined />
                  </Space>
                </Button>
              </Dropdown>
            </Space>
          </div>
          <div ref={actionSizerRef} className={assetDataStyle.actionSizer}>
            <Space>
              <Button type="primary">
                <Space>
                  {t('common.addNew')}
                  <DownOutlined />
                </Space>
              </Button>
              <Button>
                <Space>
                  {t('export')}
                  <DownOutlined />
                </Space>
              </Button>
              <Button>
                <Space>
                  {t('more')}
                  <DownOutlined />
                </Space>
              </Button>
            </Space>
          </div>

          <div className="w-full">
            <FilterBar
              attrList={propertyList}
              userList={userList}
              proxyOptions={proxyOptions}
              modelId={modelId}
              onChange={handleFilterBarChange}
              onFilterChange={handleFilterBarChange}
            />
          </div>

          <CustomTable
            style={{ marginTop: '-1px' }}
            size="small"
            rowSelection={rowSelection}
            dataSource={tableData}
            columns={currentColumns}
            pagination={pagination}
            loading={tableLoading}
            scroll={{
              x: 'calc(100vw - 400px)',
              y: storeQueryList.length > 0
                ? 'calc(100vh - 320px)'
                : 'calc(100vh - 300px)'
            }}
            fieldSetting={{
              showSetting: true,
              displayFieldKeys,
              choosableFields: columns.filter((item) => item.key !== 'action'),
            }}
            onSelectFields={onSelectFields}
            rowKey="_id"
            onChange={handleTableChange}
          />
          <FieldModal
            ref={fieldRef}
            userList={userList}
            onSuccess={updateFieldList}
          />
          <ImportInst ref={importRef} onSuccess={updateFieldList} />
          <SelectInstance
            ref={instanceRef}
            userList={userList}
            models={originModels}
            assoTypes={assoTypes}
            needFetchAssoInstIds
          />
          <ExportModal
            ref={exportRef}
            userList={userList}
            models={originModels}
            assoTypes={assoTypes}
          />
        </div>
      </div>
    </Spin>
  );
};

const AssetData = () => {
  return (
    <KeepAlive id="assetData" name="assetData">
      <AssetDataContent />
    </KeepAlive>
  );
};

export default AssetData;
