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
  Cascader,
  TablePaginationConfig,
  CascaderProps,
  Tree,
  Input,
  Empty,
} from 'antd';
import CustomTable from '@/components/custom-table';
import SearchFilter from './list/searchFilter';
import ImportInst from './list/importInst';
import SelectInstance from './detail/relationships/selectInstance';
import { DownOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import assetDataStyle from './index.module.scss';
import FieldModal from './list/fieldModal';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
const { confirm } = Modal;
import { deepClone, getAssetColumns } from '@/app/cmdb/utils/common';
import {
  GroupItem,
  ModelItem,
  ColumnItem,
  UserItem,
  Organization,
  AttrFieldType,
  RelationInstanceRef,
  AssoTypeItem,
} from '@/app/cmdb/types/assetManage';
import axios from 'axios';
import { useAuth } from '@/context/auth';
import { useCommon } from '@/app/cmdb/context/common';
import type { MenuProps } from 'antd';
import { useRouter } from 'next/navigation';
import PermissionWrapper from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useSession } from 'next-auth/react';

interface ModelTabs {
  key: string;
  label: string;
  icn: string;
}
interface FieldRef {
  showModal: (config: FieldConfig) => void;
}
interface ImportRef {
  showModal: (config: {
    subTitle: string;
    title: string;
    model_id: string;
  }) => void;
}
interface FieldConfig {
  type: string;
  attrList: AttrFieldType[];
  formInfo: any;
  subTitle: string;
  title: string;
  model_id: string;
  list: Array<any>;
}

const AssetDataContent = () => {
  const { t } = useTranslation();
  const { get, del, post, isLoading } = useApiClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const assetModelId: string = searchParams.get('modelId') || '';
  const assetClassificationId: string =
    searchParams.get('classificationId') || '';
  const commonContext = useCommon();
  const authContext = useAuth();
  const { data: session } = useSession();
  const token = session?.user?.token || authContext?.token || null;
  const tokenRef = useRef(token);
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const fieldRef = useRef<FieldRef>(null);
  const importRef = useRef<ImportRef>(null);
  const instanceRef = useRef<RelationInstanceRef>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Array<any>>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [exportLoading, setExportLoading] = useState<boolean>(false);
  const [modelGroup, setModelGroup] = useState<GroupItem[]>([]);
  const [originModels, setOriginModels] = useState<ModelItem[]>([]);
  const [groupId, setGroupId] = useState<string>('');
  const [modelId, setModelId] = useState<string>('');
  const [modelList, setModelList] = useState<ModelTabs[]>([]);
  const [propertyList, setPropertyList] = useState<AttrFieldType[]>([]);
  const [displayFieldKeys, setDisplayFieldKeys] = useState<string[]>([]);
  const [columns, setColumns] = useState<ColumnItem[]>([]);
  const [currentColumns, setCurrentColumns] = useState<ColumnItem[]>([]);
  const [assoTypes, setAssoTypes] = useState<AssoTypeItem[]>([]);
  const [queryList, setQueryList] = useState<unknown>(null);
  const [tableData, setTableData] = useState<any[]>([]);
  const [organization, setOrganization] = useState<string[]>([]);
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
    if (modelId === 'host') {
      get('/cmdb/api/instance/list_proxys/', {})
        .then((data: any[]) => {
          setProxyOptions(data || []);
        })
        .catch(() => {
          setProxyOptions([]);
        });
    }
  }, [modelId]);

  const handleExport = async (keys: string[]) => {
    try {
      setExportLoading(true);
      const response = await axios({
        url: `/api/proxy/cmdb/api/instance/${modelId}/inst_export/`,
        method: 'POST',
        responseType: 'blob',
        data: keys,
        headers: {
          Authorization: `Bearer ${tokenRef.current}`,
        },
      });
      const blob = new Blob([response.data], {
        type: response.headers['content-type'],
      });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${modelId}资产列表.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error: any) {
      message.error(error.message);
    } finally {
      setExportLoading(false);
    }
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
    if (isLoading) return;
    getModelGroup();
  }, [get, isLoading]);

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
    try {
      const data = await post(`/cmdb/api/instance/search/`, params);
      setTableData(data.insts);
      pagination.total = data.count;
      setPagination(pagination);
    } catch (error) {
      console.log(error);
    } finally {
      setTableLoading(false);
    }
  };

  const getModelGroup = async () => {
    try {
      setLoading(true);
      const [modeldata, groupData, assoType, instCount] = await Promise.all([
        get('/cmdb/api/model/'),
        get('/cmdb/api/classification/'),
        get('/cmdb/api/model/model_association_type/'),
        get('/cmdb/api/instance/model_inst_count/'),
      ]);
      setModelInstCount(instCount);
      const groups = deepClone(groupData).map((item: GroupItem) => ({
        ...item,
        list: [],
        count: 0,
      }));
      modeldata.forEach((modelItem: ModelItem) => {
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
      const _modelList = modeldata
        .filter((item: any) => item.classification_id === defaultGroupId)
        .map((item: any) => ({
          key: item.model_id,
          label: item.model_name,
          icn: item.icn,
        }));
      const defaultModelId = assetModelId || _modelList[0].key;
      setOriginModels(modeldata);
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
    const activeQueryList =
      overrideQueryList !== undefined ? overrideQueryList : queryList;
    const conditions = organization?.length
      ? [{ field: 'organization', type: 'list[]', value: organization }]
      : [];
    return {
      query_list: activeQueryList
        ? [activeQueryList, ...conditions]
        : conditions,
      page: pagination.current,
      page_size: pagination.pageSize,
      order: '',
      model_id: modelId,
      role: '',
    };
  };

  const getInitData = (id: string, overrideQueryList?: unknown) => {
    const tableParmas = getTableParams(overrideQueryList);
    const getAttrList = get(`/cmdb/api/model/${id}/attr_list/`);
    const getInstList = post('/cmdb/api/instance/search/', {
      ...tableParmas,
      model_id: id,
    });
    const getDisplayFields = get(`/cmdb/api/instance/${id}/show_field/detail/`);
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
      await post(`/cmdb/api/instance/${modelId}/show_field/settings/`, fields);
      message.success(t('successfulSetted'));
      getInitData(modelId);
    } finally {
      setLoading(false);
    }
  };

  const showDeleteConfirm = (row = { _id: '' }) => {
    confirm({
      title: t('deleteTitle'),
      content: t('deleteContent'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await del(`/cmdb/api/instance/${row._id}/`);
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
      title: t('deleteTitle'),
      content: t('deleteContent'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            const list = selectedRowKeys;
            await post('/cmdb/api/instance/batch_delete/', list);
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
      label: (
        <a onClick={() => handleExport(selectedRowKeys)}>{t('selected')}</a>
      ),
      disabled: !selectedRowKeys.length,
    },
    {
      key: 'exportCurrentPage',
      label: (
        <a onClick={() => handleExport(tableData.map((item) => item._id))}>
          {t('currentPage')}
        </a>
      ),
    },
    {
      key: 'exportAll',
      label: <a onClick={() => handleExport([])}>{t('all')}</a>,
    },
  ];

  const updateFieldList = async (id?: string) => {
    await fetchData();
    try {
      const instCount = await get('/cmdb/api/instance/model_inst_count/');
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
    const title = type === 'add' ? t('common.addNew') : t('edit');
    fieldRef.current?.showModal({
      title,
      type,
      attrList: propertyList,
      formInfo: row,
      subTitle: '',
      model_id: modelId,
      list: selectedRowKeys,
    });
  };

  const handleTableChange = (pagination = {}) => {
    setPagination(pagination);
  };

  const handleSearch = (condition: unknown) => {
    setQueryList(condition);
  };

  const checkDetail = (row = { _id: '', inst_name: '', ip_addr: '' }) => {
    const modelItem = modelList.find((item) => item.key === modelId);
    router.push(
      `/cmdb/assetData/detail/baseInfo?icn=${modelItem?.icn || ''}&model_name=${
        modelItem?.label || ''
      }&model_id=${modelId}&classification_id=${groupId}&inst_id=${
        row._id
      }&${row.inst_name ? `inst_name=${row.inst_name}` : `ip_addr=${row.ip_addr}`}`
    );
  };

  const selectOrganization: CascaderProps<Organization>['onChange'] = (
    value
  ) => {
    setOrganization(value);
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
        groupList: organizationList,
        t,
      });
      const tableColumns = [
        ...attrList,
        {
          title: t('action'),
          key: 'action',
          dataIndex: 'action',
          width: 230,
          fixed: 'right',
          render: (_: unknown, record: any) => (
            <>
              <Button
                type="link"
                className="mr-[10px]"
                onClick={() => checkDetail(record)}
              >
                {t('detail')}
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
              <PermissionWrapper
                requiredPermissions={['Edit']}
                instPermissions={record.permission}
              >
                <Button
                  type="link"
                  className="mr-[10px]"
                  onClick={() => showAttrModal('edit', record)}
                >
                  {t('edit')}
                </Button>
              </PermissionWrapper>
              <PermissionWrapper
                requiredPermissions={['Delete']}
                instPermissions={record.permission}
              >
                <Button type="link" onClick={() => showDeleteConfirm(record)}>
                  {t('delete')}
                </Button>
              </PermissionWrapper>
            </>
          ),
        },
      ];
      setColumns(tableColumns);
      const actionCol = tableColumns.find(col => col.key === 'action');
      const ordered = [
        ...tableColumns
          .filter(col => displayFieldKeys.includes(col.key as string))
          .sort((a, b) =>
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
          <a onClick={batchDeleteConfirm}>{t('batchDelete')}</a>
        </PermissionWrapper>
      ),
      disabled: !selectedRowKeys.length,
    },
  ];

  return (
    <Spin spinning={loading} wrapperClassName={assetDataStyle.assetLoading}>
      <div className={assetDataStyle.assetData}>
        <div className={`${assetDataStyle.groupSelector}`}>
          <div className={assetDataStyle.treeSearchWrapper}>
            <Input.Search
              placeholder={t('searchTxt')}
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
          <div className="flex justify-between mb-4">
            <Space>
              <Cascader
                placeholder={t('common.pleaseSelect')}
                options={organizationList}
                value={organization}
                onChange={selectOrganization}
              />
              <SearchFilter
                key={modelId}
                proxyOptions={proxyOptions}
                userList={userList}
                attrList={propertyList.filter(
                  (item) => item.attr_type !== 'organization'
                )}
                organizationList={organizationList}
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
              <Dropdown
                menu={{ items: exportItems }}
                disabled={exportLoading}
                placement="bottom"
              >
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
          <CustomTable
            size="small"
            rowSelection={rowSelection}
            dataSource={tableData}
            columns={currentColumns}
            pagination={pagination}
            loading={tableLoading}
            scroll={{ x: 'calc(100vw - 400px)', y: 'calc(100vh - 300px)' }}
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
            organizationList={organizationList}
            onSuccess={updateFieldList}
          />
          <ImportInst ref={importRef} onSuccess={updateFieldList} />
          <SelectInstance
            ref={instanceRef}
            userList={userList}
            models={originModels}
            assoTypes={assoTypes}
            organizationList={organizationList}
            needFetchAssoInstIds
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
