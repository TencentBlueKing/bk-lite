'use client';

import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Input, Button, Switch, Popconfirm, message, Tag } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import {
  ColumnItem,
  ModalRef,
  Pagination,
  TableDataItem,
  TreeItem,
  TreeSortData
} from '@/app/monitor/types';
import {
  MonitorObjectType,
  MonitorObjectItem,
  ObjectTypeFormData
} from './types';
import CustomTable from '@/components/custom-table';
import Permission from '@/components/permission';
import ObjectTypeModal from './objectTypeModal';
import ObjectModal from './objectModal';
import useObjectApi from './api';
import TreeSelector from '@/app/monitor/components/treeSelector';

const ObjectPage = () => {
  const { isLoading } = useApiClient();
  const { t } = useTranslation();
  const {
    getObjectTypes,
    getObjects,
    updateObjectTypeOrder,
    updateObjectOrder,
    updateObjectVisibility,
    deleteObject,
    deleteObjectType
  } = useObjectApi();

  const typeModalRef = useRef<ModalRef>(null);
  const objectModalRef = useRef<ModalRef>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 对象类型相关状态
  const [typeLoading, setTypeLoading] = useState(false);
  const [typeList, setTypeList] = useState<MonitorObjectType[]>([]);
  const [selectedType, setSelectedType] = useState<MonitorObjectType | null>(
    null
  );
  const [defaultSelectedKey, setDefaultSelectedKey] = useState<React.Key>('');

  // 对象列表相关状态
  const [objectLoading, setObjectLoading] = useState(false);
  const [objectList, setObjectList] = useState<MonitorObjectItem[]>([]);
  const [objectSearchText, setObjectSearchText] = useState('');
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  });

  // 将对象类型列表转换为 TreeSelector 需要的数据格式
  const treeData: TreeItem[] = useMemo(() => {
    return typeList.map((type) => ({
      title: `${type.name}（${type.object_count || 0}）`,
      key: type.id,
      label: type.id,
      children: []
    }));
  }, [typeList]);

  // 表格列配置
  const columns: ColumnItem[] = useMemo(
    () => [
      {
        title: t('monitor.object.objectName'),
        dataIndex: 'name',
        key: 'name',
        render: (_: unknown, record: TableDataItem) => (
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded flex items-center justify-center bg-[var(--color-fill-2)]">
              {record.icon ? (
                <img
                  src={`/app/assets/assetModelIcon/${record.icon}.svg`}
                  alt={record.name}
                  className="w-6 h-6"
                  onError={(e) => {
                    (e.target as HTMLImageElement).src =
                      '/app/assets/assetModelIcon/cc-default_默认.svg';
                  }}
                />
              ) : (
                <span className="text-sm">📦</span>
              )}
            </div>
            <span className="font-medium">
              {record.display_name || record.name}
            </span>
          </div>
        )
      },
      {
        title: t('monitor.object.objectId'),
        dataIndex: 'name',
        key: 'name',
        width: 180
      },
      {
        title: t('monitor.object.childObjectCount'),
        dataIndex: 'children_count',
        key: 'children_count',
        width: 100,
        render: (_: unknown, record: TableDataItem) => {
          const count = (record as MonitorObjectItem).children_count ?? 0;
          return <Tag color="blue">{count}</Tag>;
        }
      },
      {
        title: t('monitor.object.source'),
        dataIndex: 'is_builtin',
        key: 'is_builtin',
        width: 80,
        render: (_: unknown, record: TableDataItem) => {
          const isBuiltin = (record as MonitorObjectItem).is_builtin;
          return (
            <Tag color={isBuiltin ? 'default' : 'blue'}>
              {isBuiltin
                ? t('monitor.object.builtin')
                : t('monitor.object.custom')}
            </Tag>
          );
        }
      },
      {
        title: t('monitor.object.visible'),
        dataIndex: 'is_visible',
        key: 'is_visible',
        width: 100,
        render: (_: unknown, record: TableDataItem) => (
          <Switch
            checked={record.is_visible}
            onChange={(checked) =>
              handleVisibilityChange(record as MonitorObjectItem, checked)
            }
          />
        )
      },
      {
        title: t('common.actions'),
        key: 'action',
        dataIndex: 'action',
        width: 120,
        fixed: 'right',
        render: (_: unknown, record: TableDataItem) => {
          const isBuiltin = (record as MonitorObjectItem).is_builtin;
          return (
            <div className="flex gap-2">
              <Permission requiredPermissions={['Edit']}>
                <Button
                  type="link"
                  size="small"
                  disabled={isBuiltin}
                  onClick={() =>
                    openObjectModal('edit', record as MonitorObjectItem)
                  }
                >
                  {t('common.edit')}
                </Button>
              </Permission>
              <Permission requiredPermissions={['Delete']}>
                <Popconfirm
                  title={t('common.delConfirm')}
                  description={t('common.delConfirmCxt')}
                  okText={t('common.confirm')}
                  cancelText={t('common.cancel')}
                  onConfirm={() =>
                    handleDeleteObject(record as MonitorObjectItem)
                  }
                  disabled={isBuiltin}
                >
                  <Button type="link" size="small" disabled={isBuiltin}>
                    {t('common.delete')}
                  </Button>
                </Popconfirm>
              </Permission>
            </div>
          );
        }
      }
    ],
    [t, selectedType]
  );

  // 初始化加载
  useEffect(() => {
    if (!isLoading) {
      fetchObjectTypes();
    }
  }, [isLoading]);

  // 选中类型变化时加载对象列表
  useEffect(() => {
    if (selectedType) {
      fetchObjects(selectedType.id);
    }
  }, [selectedType, pagination.current, pagination.pageSize]);

  // 对象表格拖拽排序
  const onRowDragEnd = async (newList: MonitorObjectItem[]) => {
    if (!selectedType) return;
    try {
      // 构建排序数据：当前类型下的对象名称列表（按新顺序）
      const orderData = [
        {
          type: selectedType.id,
          object_list: newList.map((item) => item.name)
        }
      ];
      await updateObjectOrder(orderData);
      message.success(t('common.updateSuccess'));
      // 更新本地状态
      setObjectList(newList);
    } catch {
      // 排序失败，重新获取列表
      fetchObjects();
    }
  };

  // 获取对象类型列表
  const fetchObjectTypes = async () => {
    try {
      setTypeLoading(true);
      const data = await getObjectTypes();
      setTypeList(data || []);
      // 默认选中第一个
      if (data?.length > 0 && !selectedType) {
        setSelectedType(data[0]);
        setDefaultSelectedKey(data[0].id);
      }
    } finally {
      setTypeLoading(false);
    }
  };

  // 获取对象列表
  const fetchObjects = async (typeId?: string) => {
    const currentTypeId = typeId || selectedType?.id;
    if (!currentTypeId) return;

    // 取消上一次请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    // 创建新的 AbortController
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setObjectLoading(true);
    try {
      const params = {
        type_id: currentTypeId,
        page: pagination.current,
        page_size: pagination.pageSize,
        name: objectSearchText || undefined
      };
      const data = await getObjects(params, controller.signal);
      // 请求成功且未被取消时才更新数据和关闭 loading
      if (!controller.signal.aborted) {
        setObjectList(data?.results || []);
        setPagination((prev) => ({
          ...prev,
          total: data?.count || 0
        }));
        setObjectLoading(false);
      }
    } catch (error: any) {
      // 忽略取消请求的错误，不关闭 loading（让下一次请求控制）
      if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED') {
        return;
      }
      // 其他错误时关闭 loading
      setObjectLoading(false);
      throw error;
    }
  };

  // 选择对象类型
  const handleNodeSelect = (key: string) => {
    const type = typeList.find((t) => t.id === key);
    if (type) {
      // 取消上一次请求
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      // 立即清空右侧列表并显示 loading，避免数据闪动
      setObjectList([]);
      setObjectLoading(true);
      setSelectedType(type);
      setObjectSearchText('');
      setPagination((prev) => ({ ...prev, current: 1 }));
    }
  };

  // 处理拖拽排序
  const handleNodeDrag = async (sortData: TreeSortData[]) => {
    try {
      // sortData 格式: [{ type: 类型ID, object_list: [] }, ...]
      // 后端接口直接接受这个格式
      await updateObjectTypeOrder(sortData);
      message.success(t('common.updateSuccess'));
      fetchObjectTypes();
    } catch {
      fetchObjectTypes();
    }
  };

  // 打开对象类型弹窗
  const openTypeModal = (
    type: string,
    form: MonitorObjectType = {} as MonitorObjectType
  ) => {
    typeModalRef.current?.showModal({
      type,
      form,
      title:
        type === 'add'
          ? t('monitor.object.addType')
          : t('monitor.object.editType')
    });
  };

  // 打开对象弹窗
  const openObjectModal = (
    type: string,
    form: MonitorObjectItem = {} as MonitorObjectItem
  ) => {
    objectModalRef.current?.showModal({
      type,
      form: { ...form, type_id: selectedType?.id },
      title:
        type === 'add'
          ? t('monitor.object.addObject')
          : t('monitor.object.editObject')
    });
  };

  // 切换对象可见性
  const handleVisibilityChange = async (
    record: MonitorObjectItem,
    checked: boolean
  ) => {
    try {
      await updateObjectVisibility(record.id, checked);
      message.success(t('common.updateSuccess'));
      fetchObjects();
    } catch {
      message.error(t('common.operationFailed'));
    }
  };

  // 删除对象
  const handleDeleteObject = async (record: MonitorObjectItem) => {
    try {
      await deleteObject(record.id);
      message.success(t('common.delSuccess'));
      fetchObjects();
      fetchObjectTypes();
    } catch {
      message.error(t('common.operationFailed'));
    }
  };

  // 删除对象类型
  const handleDeleteType = async () => {
    if (!selectedType) return;

    if (objectList.length > 0) {
      message.warning(t('monitor.object.cannotDeleteTypeWithObjects'));
      return;
    }

    setTypeLoading(true);
    try {
      await deleteObjectType(selectedType.id);
      message.success(t('common.delSuccess'));
      // 删除后重新获取列表并选中第一个
      const data = await getObjectTypes();
      setTypeList(data || []);
      if (data?.length > 0) {
        setSelectedType(data[0]);
        setDefaultSelectedKey(data[0].id);
      } else {
        setSelectedType(null);
        setDefaultSelectedKey('');
      }
    } catch {
      message.error(t('common.operationFailed'));
    } finally {
      setTypeLoading(false);
    }
  };

  // 表格分页变化
  const handleTableChange = (paginationInfo: Pagination) => {
    setPagination(paginationInfo);
  };

  // 搜索对象
  const handleSearchObject = () => {
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchObjects();
  };

  // 清空搜索
  const handleClearSearch = () => {
    setObjectSearchText('');
    setPagination((prev) => ({ ...prev, current: 1 }));
    // 直接传空字符串查询，避免状态异步更新导致使用旧值
    fetchObjectsWithSearch('');
  };

  // 带搜索参数的获取对象列表
  const fetchObjectsWithSearch = async (
    searchText: string,
    typeId?: string
  ) => {
    const currentTypeId = typeId || selectedType?.id;
    if (!currentTypeId) return;

    // 取消上一次请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    // 创建新的 AbortController
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setObjectLoading(true);
    try {
      const params = {
        type_id: currentTypeId,
        page: 1,
        page_size: pagination.pageSize,
        name: searchText || undefined
      };
      const data = await getObjects(params, controller.signal);
      // 请求成功且未被取消时才更新数据和关闭 loading
      if (!controller.signal.aborted) {
        setObjectList(data?.results || []);
        setPagination((prev) => ({
          ...prev,
          current: 1,
          total: data?.count || 0
        }));
        setObjectLoading(false);
      }
    } catch (error: any) {
      // 忽略取消请求的错误，不关闭 loading（让下一次请求控制）
      if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED') {
        return;
      }
      // 其他错误时关闭 loading
      setObjectLoading(false);
      throw error;
    }
  };

  // 操作成功回调
  const handleTypeSuccess = async (
    actionType: 'add' | 'edit',
    data: ObjectTypeFormData
  ) => {
    // 重新获取列表，显示 loading
    setTypeLoading(true);
    try {
      const list = await getObjectTypes();
      setTypeList(list || []);

      if (actionType === 'add' && data.id) {
        // 新增：选中新创建的对象类型（根据后端返回的 id）
        const newType = list?.find((item) => item.id === data.id);
        if (newType) {
          setSelectedType(newType);
          setDefaultSelectedKey(newType.id);
        }
      } else if (actionType === 'edit' && data.id) {
        // 编辑：更新当前选中的对象类型信息（同步右侧标题）
        if (selectedType?.id === data.id) {
          const updatedType = list?.find((item) => item.id === data.id);
          if (updatedType) {
            setSelectedType(updatedType);
          }
        }
      }
    } finally {
      setTypeLoading(false);
    }
  };

  const handleObjectSuccess = () => {
    fetchObjects();
    fetchObjectTypes();
  };

  return (
    <div className="w-full flex overflow-hidden">
      {/* 左侧对象类型列表 */}
      <div className="h-[calc(100vh-146px)] bg-[var(--color-bg-1)] w-[220px] min-w-[220px] mr-2.5 overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-2.5 pt-5 mb-[15px]">
          <span className="font-semibold">
            {t('monitor.object.objectType')}
          </span>
          <Permission requiredPermissions={['Add']}>
            <Button
              size="small"
              icon={<PlusOutlined />}
              onClick={() => openTypeModal('add')}
              title={t('monitor.object.addType')}
            />
          </Permission>
        </div>
        <div className="flex-1 overflow-y-auto px-2.5 pb-2.5">
          <TreeSelector
            data={treeData}
            defaultSelectedKey={defaultSelectedKey}
            loading={typeLoading}
            draggable
            onNodeSelect={handleNodeSelect}
            onNodeDrag={handleNodeDrag}
          />
        </div>
      </div>

      {/* 右侧对象列表 */}
      <div className="flex-1 flex flex-col bg-[var(--color-bg-1)] p-5 overflow-hidden">
        {/* 标题栏 */}
        <div className="flex items-center justify-between mb-[15px]">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold m-0">
              {selectedType?.name || ''}
            </h2>
            {/* 非内置类型才显示编辑和删除按钮 */}
            {selectedType && !selectedType.is_builtin && (
              <div className="flex gap-1">
                <Permission requiredPermissions={['Edit']}>
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    className="text-[var(--color-primary)]"
                    onClick={() => openTypeModal('edit', selectedType)}
                    title={t('monitor.object.editType')}
                  />
                </Permission>
                <Permission requiredPermissions={['Delete']}>
                  <Popconfirm
                    title={t('common.delConfirm')}
                    description={t('monitor.object.deleteTypeConfirm')}
                    okText={t('common.confirm')}
                    cancelText={t('common.cancel')}
                    onConfirm={handleDeleteType}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      className="text-[var(--color-primary)]"
                      title={t('monitor.object.deleteType')}
                    />
                  </Popconfirm>
                </Permission>
              </div>
            )}
          </div>
        </div>

        {/* 工具栏 */}
        <div className="flex items-center justify-between mb-4">
          <Input
            allowClear
            className="w-80"
            placeholder={t('monitor.object.searchObjectId')}
            value={objectSearchText}
            onChange={(e) => setObjectSearchText(e.target.value)}
            onPressEnter={handleSearchObject}
            onClear={handleClearSearch}
          />
          <Permission requiredPermissions={['Add']}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => openObjectModal('add')}
            >
              {t('monitor.object.addObject')}
            </Button>
          </Permission>
        </div>

        {/* 对象表格 */}
        <div className="flex-1 overflow-hidden">
          <CustomTable
            scroll={{ y: 'calc(100vh - 390px)' }}
            columns={columns}
            dataSource={objectList}
            pagination={pagination}
            loading={objectLoading}
            rowKey="id"
            rowDraggable={true}
            expandable={{ childrenColumnName: '_no_children_' }}
            onRowDragEnd={onRowDragEnd}
            onChange={handleTableChange}
          />
        </div>
      </div>

      {/* 弹窗组件 */}
      <ObjectTypeModal ref={typeModalRef} onSuccess={handleTypeSuccess} />
      <ObjectModal
        ref={objectModalRef}
        typeId={selectedType?.id}
        onSuccess={handleObjectSuccess}
      />
    </div>
  );
};

export default ObjectPage;
