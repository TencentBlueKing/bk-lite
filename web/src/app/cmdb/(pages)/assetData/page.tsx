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
import CustomTable from '@/components/custom-table';
import GroupTreeSelector from '@/components/group-tree-select';
import SearchFilter from './list/searchFilter';
import FilterBar from './list/FilterBar';
import { useAssetDataStore, type FilterItem } from '@/app/cmdb/store';
import ImportInst from './list/importInst';
import SelectInstance from './detail/relationships/selectInstance';
import ExportModal from './components/exportModal';
import { ExportModalRef } from '@/app/cmdb/types/assetData';
import { DownOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import assetDataStyle from './index.module.scss';
import FieldModal from './list/fieldModal';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
const { confirm } = Modal;
import { deepClone, getAssetColumns } from '@/app/cmdb/utils/common';
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
import { useCommon } from '@/app/cmdb/context/common';
import type { MenuProps } from 'antd';
import { useRouter } from 'next/navigation';
import PermissionWrapper from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import {
  useModelApi,
  useClassificationApi,
  useInstanceApi,
} from '@/app/cmdb/api';

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
  const searchParams = useSearchParams();
  const assetModelId: string = searchParams.get('modelId') || '';
  const assetClassificationId: string =
    searchParams.get('classificationId') || '';
  const commonContext = useCommon();
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const modelListFromContext = commonContext?.modelList || [];
  const fieldRef = useRef<FieldRef>(null);
  const importRef = useRef<ImportRef>(null);
  const instanceRef = useRef<RelationInstanceRef>(null);
  const exportRef = useRef<ExportModalRef>(null);
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
  const [queryList, setQueryList] = useState<unknown>(null);
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

  const addInstItems: MenuProps['items'] = [
    {
      key: '1',
      label: <a onClick={() => showAttrModal('add')}>{t('common.add')}</a>,
    },
    {
      key: '2',
      label: <a onClick={showImportModal}>{t('import')}</a>,
    },
  ];

  useEffect(() => {
    if (modelListFromContext.length > 0) {
      getModelGroup();
    }
  }, [modelListFromContext]);

  useEffect(() => {
    if (modelId) {
      setSelectedTreeKeys([modelId]);
      fetchData();
    }
  }, [pagination?.current, pagination?.pageSize, queryList, organization]);

  useEffect(() => {
    setExpandedTreeKeys(
      modelGroup.map((item) => `group:${item.classification_id}`)
    );
  }, [modelGroup]);

  const fetchData = async () => {
    setTableLoading(true);
    const params = getTableParams();
    let caughtError: { name?: string } | null = null;
    try {
      // console.log("test6:params", params);
      const data = await searchInstances(params);
      setTableData(data.insts);
      pagination.total = data.count;
      setPagination(pagination);
    } catch (error) {
      caughtError = error as { name?: string } | null;
    } finally {
      if (caughtError && caughtError?.name === "CanceledError") return;
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
      setModelInstCount(instCount);
      const groups = deepClone(groupData).map((item: GroupItem) => ({
        ...item,
        list: [],
        count: 0,
      }));
      modelListFromContext.forEach((modelItem: ModelItem) => {
        const target = groups.find(
          (item: GroupItem) =>
            item.classification_id === modelItem.classification_id
        );
        if (target) {
          target.list.push(modelItem);
          target.count++;
        }
      });
      const defaultGroupId =
        assetClassificationId || groupData[0].classification_id;
      setGroupId(defaultGroupId);
      setModelGroup(groups);
      const _modelList = modelListFromContext
        .filter((item: any) => item.classification_id === defaultGroupId)
        .map((item: any) => ({
          key: item.model_id,
          label: item.model_name,
          icn: item.icn,
        }));
      const defaultModelId = assetModelId || _modelList[0].key;
      setOriginModels(modelListFromContext);
      setAssoTypes(assoType);
      setModelList(_modelList);
      setModelId(defaultModelId);
      setSelectedTreeKeys([defaultModelId]);
      getInitData(defaultModelId);
      router.push(
        `/cmdb/assetData?modelId=${defaultModelId}&classificationId=${defaultGroupId}`
      );
    } catch {
      setLoading(false);
    }
  };

  const getTableParams = (overrideQueryList?: unknown) => {
    const activeQueryList = overrideQueryList !== undefined
      ? overrideQueryList
      : queryList || null;

    const conditions = organization?.length
      ? [{ field: 'organization', type: 'list[]', value: organization }]
      : [];

    const caseSensitive = useAssetDataStore.getState().case_sensitive;

    return {
      query_list: activeQueryList
        ? [activeQueryList, ...conditions]
        : conditions,
      page: pagination.current,
      page_size: pagination.pageSize,
      order: '',
      model_id: modelId,
      role: '',
      case_sensitive: caseSensitive,
    };
  };

  const getInitData = (id: string, overrideQueryList?: unknown) => {
    const tableParmas = getTableParams(overrideQueryList);

    // 获取模型属性列表的接口（除了编辑和新增弹窗）
    const getAttrList = getModelAttrList(id);

    // 编辑弹窗中，获取模型属性分组列表的接口
    getModelAttrGroupsFullInfo(id).then((res) => {
      setPropertyListGroups(res.groups);
    }).catch((err) => {
      console.error('Failed:', err);
      message.error(t('common.getFailed'));
    });



    const getInstList = searchInstances({
      ...tableParmas,
      model_id: id,
    });
    const getDisplayFields = getInstanceShowFieldDetail(id);
    setLoading(true);
    try {
      Promise.all([getAttrList, getInstList, getDisplayFields])
        .then((res) => {
          pagination.total = res[1].count;
          const tableList = res[1].insts;
          const fieldKeys =
            res[2]?.show_fields ||
            res[0].map((item: AttrFieldType) => item.attr_id);
          setDisplayFieldKeys(fieldKeys);
          setPropertyList(res[0]);
          setTableData(tableList);
          setPagination(pagination);
        })
        .finally(() => {
          setLoading(false);
        });
    } catch {
      setLoading(false);
    }
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
      getInitData(modelId);
    } finally {
      setLoading(false);
    }
  };

  const showDeleteConfirm = (row = { _id: '' }) => {
    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await deleteInstance(row._id);
            message.success(t('successfullyDeleted'));
            if (pagination?.current) {
              pagination.current > 1 &&
                tableData.length === 1 &&
                pagination.current--;
            }
            setSelectedRowKeys([]);
            fetchData();
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const batchDeleteConfirm = () => {
    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            const list = selectedRowKeys;
            await batchDeleteInstances(list);
            message.success(t('successfullyDeleted'));
            if (pagination?.current) {
              pagination.current > 1 &&
                tableData.length === 1 &&
                pagination.current--;
            }
            setSelectedRowKeys([]);
            fetchData();
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const exportItems: MenuProps['items'] = [
    {
      key: 'batchExport',
      label: <a onClick={() => handleExport('selected')}>{t('selected')}</a>,
      disabled: !selectedRowKeys.length,
    },
    {
      key: 'exportCurrentPage',
      label: (
        <a onClick={() => handleExport('currentPage')}>{t('currentPage')}</a>
      ),
    },
    {
      key: 'exportAll',
      label: <a onClick={() => handleExport('all')}>{t('all')}</a>,
    },
  ];

  const updateFieldList = async (id?: string) => {
    await fetchData();
    try {
      const instCount = await getModelInstanceCount();
      setModelInstCount(instCount);
    } catch {
      console.error('Failed to fetch model instance count');
    }
    if (id) {
      showInstanceModal({
        _id: id,
      });
    }
  };

  const showAttrModal = (type: string, row = {}) => {
    const title = type === 'add' ? t('common.addNew') : t('common.edit');
    fieldRef.current?.showModal({
      title,
      type,
      // attrList: propertyList,
      attrList: propertyListGroups,
      formInfo: row,
      subTitle: '',
      model_id: modelId,
      list: selectedRowKeys,
    });
  };

  const showCopyModal = (record: any) => {
    const copyData = { ...record };
    const excludeFields = [
      '_id',
      'inst_id',
      'id',
      'created_at',
      'updated_at',
      'created_by',
      'updated_by',
    ];
    excludeFields.forEach((field) => {
      delete copyData[field];
    });

    // 从分组中提取所有属性
    const allAttrs = propertyListGroups.flatMap((group) => group.attrs || []);
    allAttrs.forEach((attr) => {
      if (attr.is_required && attr.is_only && copyData[attr.attr_id]) {
        copyData[attr.attr_id] = `${copyData[attr.attr_id]}_copy`;
      }
    });

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

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleSearch = (condition: FilterItem | null, _searchValue?: any) => {
    // console.log("test1", condition);

    const addFilter = useAssetDataStore.getState().add;
    const removeFilter = useAssetDataStore.getState().remove;
    const updateFilter = useAssetDataStore.getState().update;
    const currentList = useAssetDataStore.getState().query_list;

    // 如果 condition 为 null 或没有 type 属性，说明要清除对应的筛选条件
    const isClearCondition = !condition || !condition.type

    if (isClearCondition) {
      const fieldToRemove = condition?.field;
      if (fieldToRemove) {
        // 找到对应字段的索引并删除
        const indexToRemove = currentList.findIndex((item) => item.field === fieldToRemove);
        if (indexToRemove !== -1) {
          removeFilter(indexToRemove);
        }
      }
      return;
    }

    // 检查是否已存在相同 field 的筛选条件
    const existingIndex = currentList.findIndex(
      (item) => item.field === condition.field
    );

    if (existingIndex !== -1) {
      // 如果已存在，更新该条件
      updateFilter(existingIndex, condition);
    } else {
      // 如果不存在，添加新条件
      addFilter(condition);
    }
  };

  const storeQueryList = useAssetDataStore((state) => state.query_list);

  // 监听 store 的 query_list 变化，同步到 queryList 状态（用于查询）
  useEffect(() => {
    if (storeQueryList.length === 0) {
      setQueryList(null);
    } else if (storeQueryList.length === 1) {
      // 单个条件
      setQueryList(storeQueryList[0]);
    } else {
      // console.log("test8:storeQueryList", storeQueryList);
      // 多个条件
      setQueryList(storeQueryList);
    }
  }, [storeQueryList]);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleFilterBarChange = (_filters: FilterItem[]) => {
  };

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
        <EllipsisWithTooltip
          text={modelName}
          className={assetDataStyle.treeLabel}
        />
        <span className="ml-1 text-gray-400">
          ({modelInstCount[modelId] || 0})
        </span>
      </div>
    ),
    [modelInstCount]
  );

  const filterTreeNodes = useCallback(
    (nodes: any[], searchText: string) => {
      if (!searchText) return nodes;

      return nodes.reduce((filtered: any[], node) => {
        const matchesSearch = node.content
          .toLowerCase()
          .includes(searchText.toLowerCase());

        if (node.children) {
          const filteredChildren = filterTreeNodes(node.children, searchText);
          if (filteredChildren.length > 0 || matchesSearch) {
            filtered.push({
              ...node,
              children: filteredChildren.map((child) => ({
                ...child,
                title: renderModelTitle(child.content, child.key),
              })),
            });
          }
        } else if (matchesSearch) {
          filtered.push(node);
        }

        return filtered;
      }, []);
    },
    [renderModelTitle]
  );

  const handleTreeSearch = useCallback(
    (searchText: string) => {
      setTreeSearchText(searchText);

      const treeData = modelGroup.map((group) => ({
        title: group.classification_name,
        content: group.classification_name,
        key: `group:${group.classification_id}`,
        children: group.list.map((item) => ({
          content: item.model_name,
          title: renderModelTitle(item.model_name, item.model_id),
          key: item.model_id,
        })),
      }));

      const filtered = filterTreeNodes(treeData, searchText);
      setFilteredTreeData(filtered);

      if (searchText) {
        const getAllKeys = (nodes: any[]): string[] => {
          return nodes.reduce((keys: string[], node) => {
            keys.push(node.key);
            if (node.children) {
              keys.push(...getAllKeys(node.children));
            }
            return keys;
          }, []);
        };
        setExpandedTreeKeys(getAllKeys(filtered));
      } else {
        setExpandedTreeKeys(
          modelGroup.map((item) => `group:${item.classification_id}`)
        );
      }
    },
    [modelGroup, filterTreeNodes]
  );

  useEffect(() => {
    const treeData = modelGroup.map((group) => ({
      title: group.classification_name,
      key: `group:${group.classification_id}`,
      children: group.list.map((item) => ({
        content: item.model_name,
        title: renderModelTitle(item.model_name, item.model_id),
        key: item.model_id,
      })),
    }));
    setFilteredTreeData(treeData);
  }, [modelGroup, renderModelTitle]);

  const onSelectUnified = (selectedKeys: React.Key[]) => {
    // console.log("test7");
    // 同时清理store中的query_list和searchAttr
    useAssetDataStore.getState().clear();
    useAssetDataStore.setState((state) => ({
      ...state,
      searchAttr: "",
    }));

    if (!selectedKeys.length) return;
    const key = selectedKeys[0] as string;
    if (key === modelId) return;
    if (key.startsWith('group:')) return;

    setQueryList(null);
    setSelectedTreeKeys([key]);
    setModelId(key);
    setSelectedRowKeys([]);
    setPagination({ ...pagination, current: 1 });
    modelGroup.forEach((group) => {
      if (group.list.some((item) => item.model_id === key)) {
        setGroupId(group.classification_id);
        const newModelList = group.list.map((item) => ({
          key: item.model_id,
          label: item.model_name,
          icn: item.icn,
        }));
        setModelList(newModelList);
        router.push(
          `/cmdb/assetData?modelId=${key}&classificationId=${group.classification_id}`
        );
      }
    });
    getInitData(key, null);
  };

  useEffect(() => {
    if (propertyList.length) {
      const attrList = getAssetColumns({
        attrList: propertyList,
        userList,
        t,
      });
      const tableColumns = [
        ...attrList,
        {
          title: t('common.actions'),
          key: 'action',
          dataIndex: 'action',
          width: 280,
          fixed: 'right',
          render: (_: unknown, record: any) => (
            <>
              <Button
                type="link"
                className="mr-[10px]"
                onClick={() => checkDetail(record)}
              >
                {t('common.detail')}
              </Button>
              <PermissionWrapper
                requiredPermissions={['Add Associate']}
                instPermissions={record.permission}
              >
                <Button
                  type="link"
                  className="mr-[10px]"
                  onClick={() => showInstanceModal(record)}
                >
                  {t('Model.association')}
                </Button>
              </PermissionWrapper>
              <PermissionWrapper requiredPermissions={['Add']}>
                <Button
                  type="link"
                  className="mr-[10px]"
                  onClick={() => showCopyModal(record)}
                >
                  {t('common.copy')}
                </Button>
              </PermissionWrapper>
              <PermissionWrapper
                requiredPermissions={['Edit']}
                instPermissions={record.permission}
              >
                <Button
                  type="link"
                  className="mr-[10px]"
                  onClick={() => showAttrModal('edit', record)}
                >
                  {t('common.edit')}
                </Button>
              </PermissionWrapper>
              <PermissionWrapper
                requiredPermissions={['Delete']}
                instPermissions={record.permission}
              >
                <Button type="link" onClick={() => showDeleteConfirm(record)}>
                  {t('common.delete')}
                </Button>
              </PermissionWrapper>
            </>
          ),
        },
      ];
      // tableColumns是表格的列配置，包括action列
      setColumns(tableColumns);
      const actionCol = tableColumns.find((col) => col.key === 'action');
      const ordered = [
        ...tableColumns
          .filter((col) => displayFieldKeys.includes(col.key as string))
          .sort(
            (a, b) =>
              displayFieldKeys.indexOf(a.key as string) -
              displayFieldKeys.indexOf(b.key as string)
          ),
        ...(actionCol ? [actionCol] : []),
      ];
      setCurrentColumns(ordered);
    }
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
        <div className={assetDataStyle.assetList}>
          {/* 搜索行 */}
          <div className={`flex justify-between ${storeQueryList.length === 0 ? 'mb-4' : ''}`}>
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
              <SearchFilter
                key={modelId}
                proxyOptions={proxyOptions}
                userList={userList}
                attrList={propertyList.filter(
                  (item) => item.attr_type !== 'organization'
                )}
                onSearch={handleSearch}
              />
            </Space>
            <Space>
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
              <Dropdown
                menu={{ items: batchOperateItems }}
                disabled={!selectedRowKeys.length}
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
          {/* 筛选行 */}
          <div className="w-full">
            <FilterBar
              attrList={propertyList}
              userList={userList}
              proxyOptions={proxyOptions}
              onChange={handleFilterBarChange}
              onFilterChange={handleFilterBarChange}
            />
          </div>
          {/* 表格 */}
          <CustomTable
            style={{ marginTop: '-1px' }}
            size="small"
            rowSelection={rowSelection}
            dataSource={tableData}
            columns={currentColumns}
            pagination={pagination}
            loading={tableLoading}
            // 表格滚动高度（根据查询条件变化）
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
