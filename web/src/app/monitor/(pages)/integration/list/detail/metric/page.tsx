'use client';
import React, { useEffect, useState, useRef } from 'react';
import { EditOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  Input,
  Button,
  Popconfirm,
  message,
  Spin,
  Segmented,
  Empty,
  Pagination,
  Tag
} from 'antd';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import metricStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import {
  ColumnItem,
  ModalRef,
  IntegrationItem,
  ObjectItem,
  MetricItem
} from '@/app/monitor/types';
import { MetricListItem, DimensionItem } from '@/app/monitor/types/integration';
import Collapse from '@/components/collapse';
import GroupModal from './groupModal';
import MetricModal from './metricModal';
import { useSearchParams } from 'next/navigation';
import Permission from '@/components/permission';
import {
  needsTagsEntry,
  getObjectTypeByName
} from '@/app/monitor/utils/monitorObject';
import { cloneDeep } from 'lodash';
import { buildIfmibMetricView, getDefaultMetricGroupOpenState } from './ifmibMetricView';

const Configure = () => {
  const { isLoading } = useApiClient();
  const { getMonitorObject, getMetricsGroup, getMonitorMetrics } =
    useMonitorApi();
  const {
    updateMetricsGroup,
    updateMonitorMetrics,
    deleteMonitorMetrics,
    deleteMetricsGroup
  } = useIntegrationApi();
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const groupName = searchParams.get('name') || '';
  const groupId = searchParams.get('id');
  const pluginID = searchParams.get('plugin_id') || '';
  const templateType = searchParams.get('template_type') || '';
  const enableIfmib = searchParams.get('enable_ifmib') !== 'false';
  const groupRef = useRef<ModalRef>(null);
  const metricRef = useRef<ModalRef>(null);
  const [searchText, setSearchText] = useState<string>('');
  const [metricData, setMetricData] = useState<MetricListItem[]>([]);
  const [filteredMetricData, setFilteredMetricData] = useState<
    MetricListItem[]
  >([]);
  const [metrics, setMetrics] = useState<MetricItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [metricPage, setMetricPage] = useState(1);
  const [metricCount, setMetricCount] = useState(0);
  // 保留接口返回的真实分组供指标编辑使用。
  const [apiGroupList, setApiGroupList] = useState<MetricListItem[]>([]);
  const [activeTab, setActiveTab] = useState<string>('');
  const [items, setItems] = useState<IntegrationItem[]>([]);
  const [draggingItemId, setDraggingItemId] = useState<string | null>(null);
  const [dragOverTargetId, setDragOverTargetId] = useState<string | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [groupConfirmLoading, setGroupConfirmLoading] = useState(false);
  const [showTabs, setShowTabs] = useState<boolean>(false);
  const metricTableRef = useRef<HTMLDivElement>(null);
  const manuallyClosedGroupIds = useRef<Set<string>>(new Set());
  const metricCatalogAbortRef = useRef<AbortController | null>(null);
  const canReorderCatalog = metricCount <= 100 && !searchText.trim();

  useEffect(() => () => metricCatalogAbortRef.current?.abort(), []);

  const columns: ColumnItem[] = [
    {
      title: t('common.id'),
      dataIndex: 'name',
      width: 120,
      key: 'name',
      ellipsis: true
    },
    {
      title: t('common.name'),
      dataIndex: 'display_name',
      width: 120,
      key: 'display_name',
      ellipsis: true,
      render: (_, record) => (
        <div className="flex items-center gap-1 overflow-hidden">
          <span className="truncate">{record.display_name || '--'}</span>
        </div>
      )
    },
    {
      title: t('monitor.integrations.dimension'),
      dataIndex: 'dimensions',
      width: 100,
      key: 'dimensions',
      ellipsis: true,
      render: (_, record) => (
        <>
          {record.dimensions?.length
            ? record.dimensions
              .map((item: DimensionItem) => item.name)
              .join(',')
            : '--'}
        </>
      )
    },
    {
      title: t('monitor.integrations.dataType'),
      dataIndex: 'data_type',
      key: 'data_type',
      width: 100,
      render: (value: string) => (
        <>{value === 'Enum'
          ? t('monitor.integrations.enum')
          : value === 'Number'
            ? t('monitor.integrations.number')
            : value}</>
      )
    },
    {
      title: t('common.unit'),
      dataIndex: 'unit',
      width: 80,
      key: 'unit',
      render: (_, record) => (
        <>{record.data_type === 'Enum' ? '--' : record.unit || '--'}</>
      )
    },
    {
      title: t('common.descripition'),
      dataIndex: 'display_description',
      key: 'display_description',
      width: 150
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      fixed: 'right',
      width: 110,
      render: (_, record) =>
        record.is_pre ? (
          <Button type="link" onClick={() => openMetricModal('view', record)}>
            {t('common.view')}
          </Button>
        ) : (
          <>
            <Permission
              requiredPermissions={['Edit Metric']}
              className="mr-[10px]"
            >
              <Button
                type="link"
                onClick={() => openMetricModal('edit', record)}
              >
                {t('common.edit')}
              </Button>
            </Permission>
            <Permission requiredPermissions={['Delete Metric']}>
              <Popconfirm
                title={t('common.deleteTitle')}
                description={t('common.deleteContent')}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                okButtonProps={{ loading: confirmLoading }}
                onConfirm={() => handleDeleteConfirm(record as MetricItem)}
              >
                <Button type="link">{t('common.delete')}</Button>
              </Popconfirm>
            </Permission>
          </>
        )
    }
  ];

  useEffect(() => {
    if (isLoading) return;
    getObjects();
  }, [isLoading, enableIfmib]);

  const getObjects = async () => {
    setLoading(true);
    let _objId = '';
    try {
      const data = await getMonitorObject();
      if (templateType !== 'pull' && needsTagsEntry(groupName, data)) {
        setShowTabs(true);
        const objectType = getObjectTypeByName(groupName, data);
        const _items = data
          .filter((item: ObjectItem) => item.type === objectType)
          .sort((a: ObjectItem, b: ObjectItem) => a.id - b.id)
          .map((item: ObjectItem) => ({
            label: item.display_name,
            value: item.id
          }));
        _objId = _items[0]?.value;
        setItems(_items);
      } else {
        setShowTabs(false);
        _objId = groupId || '';
      }
      setActiveTab(_objId);
      getInitData(_objId);
    } catch {
      setLoading(false);
    }
  };

  const handleDeleteConfirm = async (row: MetricItem) => {
    setConfirmLoading(true);
    try {
      await deleteMonitorMetrics(row.id);
      message.success(t('common.successfullyDeleted'));
      getInitData(activeTab, true);
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleGroupDeleteConfirm = async (row: MetricListItem) => {
    setGroupConfirmLoading(true);
    try {
      await deleteMetricsGroup(row.id);
      message.success(t('common.successfullyDeleted'));
      getInitData(activeTab, true);
    } finally {
      setGroupConfirmLoading(false);
    }
  };

  const getInitData = async (
    objId = activeTab,
    preserveState = false,
    page = metricPage,
    keyword = searchText.trim()
  ) => {
    const params = {
      monitor_object_id: +objId,
      monitor_plugin_id: +pluginID,
      ...(keyword ? { keyword } : {})
    };
    metricCatalogAbortRef.current?.abort();
    const abortController = new AbortController();
    metricCatalogAbortRef.current = abortController;
    const config = { signal: abortController.signal };
    setLoading(true);
    const currentOpenState = preserveState
      ? new Map(filteredMetricData.map((g) => [g.id, g.isOpen]))
      : null;

    if (!preserveState) {
      setSearchText('');
      manuallyClosedGroupIds.current.clear();
    }
    try {
      const [groupPage, metricsPage] = await Promise.all([
        getMetricsGroup(params, config),
        getMonitorMetrics({ ...params, include_ifmib: enableIfmib, page }, config)
      ]);
      if (abortController.signal.aborted) return;
      const rawGroupList: MetricListItem[] = (
        metricsPage.metric_groups || groupPage.items
      ).map((group) => ({
        ...group,
        id: String(group.id),
        name: group.name || '',
        is_pre: group.is_pre === true,
        child: []
      }));
      setMetricCount(metricsPage.count);
      setApiGroupList(rawGroupList);
      const metricView = buildIfmibMetricView(
        rawGroupList,
        metricsPage.items,
        enableIfmib,
        (key) => t(key)
      );
      const defaultOpenState = getDefaultMetricGroupOpenState(metricView);
      const groupData = metricView.map((group) => ({
        ...group,
        isOpen: currentOpenState
          ? (currentOpenState.get(group.id) ?? defaultOpenState.get(group.id))
          : defaultOpenState.get(group.id)
      }));
      setMetrics(groupData.flatMap((group) => group.child));
      setMetricData(groupData);
      setFilteredMetricData(groupData);
    } catch {
      if (!abortController.signal.aborted) {
        setMetricData([]);
        setFilteredMetricData([]);
      }
    } finally {
      if (metricCatalogAbortRef.current === abortController) {
        setLoading(false);
      }
    }
  };

  const onSearchTxtChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };

  const onTxtPressEnter = () => {
    setMetricPage(1);
    getInitData(activeTab, true, 1, searchText.trim());
  };

  const onTxtClear = () => {
    setSearchText('');
    setMetricPage(1);
    getInitData(activeTab, true, 1, '');
  };

  const openGroupModal = (type: string, row = {}) => {
    const title = t(
      type === 'add'
        ? 'monitor.integrations.addGroup'
        : 'monitor.integrations.editGroup'
    );
    groupRef.current?.showModal({
      title,
      type,
      form: row
    });
  };

  const openMetricModal = (type: string, row = {}) => {
    const title = t(
      type === 'add'
        ? 'monitor.integrations.addMetric'
        : type === 'view'
          ? 'monitor.integrations.viewMetric'
          : 'monitor.integrations.editMetric'
    );
    metricRef.current?.showModal({
      title,
      type,
      form: row
    });
  };

  const operateGroup = () => {
    getInitData(activeTab, true);
  };

  const operateMtric = () => {
    getInitData(activeTab, true);
  };

  const onTabChange = (val: string) => {
    setMetricData([]);
    setActiveTab(val);
    setMetricPage(1);
    getInitData(val, false, 1);
  };

  const onMetricPageChange = (page: number) => {
    setMetricPage(page);
    getInitData(activeTab, true, page, searchText.trim());
  };

  const onDragStart = (e: React.DragEvent<HTMLDivElement>, id: string) => {
    e.dataTransfer.effectAllowed = 'move';
    setDraggingItemId(id);
  };

  const onDragEnd = () => {
    setDraggingItemId(null);
    setDragOverTargetId(null);
  };

  const onDragOver = (e: React.DragEvent<HTMLDivElement>, targetId: string) => {
    if (draggingItemId) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      setDragOverTargetId(targetId);
      if (
        dragOverTargetId === targetId &&
        draggingItemId !== dragOverTargetId
      ) {
        setMetricData((prev) =>
          prev.map((item) =>
            item.id === targetId ? { ...item, isOpen: false } : item
          )
        );
      }
    }
  };

  const onDrop = async (
    e: React.DragEvent<HTMLDivElement>,
    targetId: string
  ) => {
    e.preventDefault();
    setDragOverTargetId(null);
    if (!canReorderCatalog) return;
    if (draggingItemId && draggingItemId !== targetId) {
      const draggingIndex = metricData.findIndex(
        (item) => item.id === draggingItemId
      );
      const targetIndex = metricData.findIndex((item) => item.id === targetId);
      if (draggingIndex !== -1 && targetIndex !== -1) {
        const reorderedData = cloneDeep<MetricListItem[]>(metricData);
        const [draggedItem] = reorderedData.splice(draggingIndex, 1);
        reorderedData.splice(targetIndex, 0, draggedItem);
        try {
          setLoading(true);
          const updatedOrder = reorderedData
            .filter((item: MetricListItem) => !item.is_pre)
            .map(
              (item: MetricListItem, index: number) => ({
                id: Number(item.id),
                sort_order: index
              })
            );
          await updateMetricsGroup(updatedOrder);
          message.success(t('common.updateSuccess'));
          getInitData(activeTab, true);
        } catch {
          setLoading(false);
        }
      }
      setDraggingItemId(null);
    }
  };

  const onRowDragEnd = async (data?: MetricItem[]) => {
    if (!canReorderCatalog) return;
    setLoading(true);
    const orderedData = [...(data || [])];
    metrics
      .filter((metricItem) => !metricItem.is_pre)
      .forEach((metricItem) => {
        if (!orderedData.map((item) => item.id).includes(metricItem.id)) {
          orderedData.push(metricItem);
        }
      });
    const updatedOrder = orderedData
      .filter((item: MetricItem) => !item.is_pre)
      .map((item: MetricItem, index: number) => ({
        id: item.id,
        sort_order: index
      }));

    updateMonitorMetrics(updatedOrder)
      .then(() => {
        message.success(t('common.updateSuccess'));
        getInitData(activeTab, true);
      })
      .catch(() => {
        setLoading(false);
      });
  };

  const onToggle = (id: string, isOpen: boolean) => {
    if (isOpen) {
      manuallyClosedGroupIds.current.delete(id);
    } else {
      manuallyClosedGroupIds.current.add(id);
    }
    setMetricData((prev) =>
      prev.map((item) => (item.id === id ? { ...item, isOpen } : item))
    );
    setFilteredMetricData((prev) =>
      prev.map((item) => (item.id === id ? { ...item, isOpen } : item))
    );
  };

  const autoExpandVisibleGroups = () => {
    const container = metricTableRef.current;
    if (!container || searchText.trim()) return;
    const containerRect = container.getBoundingClientRect();
    const visibleGroupIds = Array.from(
      container.querySelectorAll<HTMLElement>('[data-metric-group-id]')
    )
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.top < containerRect.bottom && rect.bottom > containerRect.top;
      })
      .map((element) => element.dataset.metricGroupId)
      .filter((id): id is string => Boolean(id));

    if (!visibleGroupIds.length) return;
    const shouldOpen = new Set(
      visibleGroupIds.filter((id) => !manuallyClosedGroupIds.current.has(id))
    );
    if (!shouldOpen.size) return;
    const openVisibleGroups = (groups: MetricListItem[]) => groups.map((group) => (
      shouldOpen.has(group.id) && !group.isOpen ? { ...group, isOpen: true } : group
    ));
    setMetricData(openVisibleGroups);
    setFilteredMetricData(openVisibleGroups);
  };

  return (
    <div className={metricStyle.metric}>
      {showTabs && (
        <Segmented
          className="mb-[20px] custom-tabs"
          value={activeTab}
          options={items}
          onChange={onTabChange}
        />
      )}
      <p className="mb-[10px] text-[var(--color-text-2)]">
        {t('monitor.integrations.metricTitle')}
      </p>
      <div className="flex items-center justify-between mb-[15px]">
        <Input
          className="w-[400px]"
          placeholder={t('monitor.integrations.searchMetricPlaceholder')}
          value={searchText}
          allowClear
          onChange={onSearchTxtChange}
          onPressEnter={onTxtPressEnter}
          onClear={onTxtClear}
        />
        <div>
          <Permission requiredPermissions={['Add Group']} className="mr-[8px]">
            <Button type="primary" onClick={() => openGroupModal('add')}>
              {t('monitor.integrations.addGroup')}
            </Button>
          </Permission>
          <Permission requiredPermissions={['Add Metric']}>
            <Button onClick={() => openMetricModal('add')}>
              {t('monitor.integrations.addMetric')}
            </Button>
          </Permission>
        </div>
      </div>
      <Spin spinning={loading}>
        <div
          ref={metricTableRef}
          onScroll={autoExpandVisibleGroups}
          className={metricStyle.metricTable}
          style={{
            height: showTabs ? 'calc(100vh - 396px)' : 'calc(100vh - 346px)'
          }}
        >
          {!!filteredMetricData.length ? (
            filteredMetricData.map((metricItem) => (
              <div key={metricItem.id} data-metric-group-id={metricItem.id}>
                <Collapse
                className={`mb-[10px] ${
                  dragOverTargetId === metricItem.id &&
                  draggingItemId !== dragOverTargetId
                    ? 'border-t-[1px] border-blue-200'
                    : ''
                }`}
                sortable={!metricItem.is_pre && canReorderCatalog}
                dragHandleOnly
                onDragStart={(e) => onDragStart(e, metricItem.id)}
                onDragEnd={onDragEnd}
                onDragOver={(e) => onDragOver(e, metricItem.id)}
                onDrop={(e) => onDrop(e, metricItem.id)}
                title={
                  <div className="flex items-center gap-2">
                    <span>{metricItem.display_name || ''}</span>
                    {metricItem.is_ifmib_group === true && (
                      <Tag className="m-0" color="blue">
                        IF-MIB
                      </Tag>
                    )}
                  </div>
                }
                isOpen={metricItem.isOpen}
                onToggle={(isOpen) => onToggle(metricItem.id, isOpen)}
                icon={
                  <div>
                    <Permission requiredPermissions={['Edit Group']}>
                      <Button
                        type="link"
                        size="small"
                        disabled={metricItem.is_pre}
                        icon={<EditOutlined />}
                        onClick={() => openGroupModal('edit', metricItem)}
                      ></Button>
                    </Permission>
                    <Permission requiredPermissions={['Edit Group']}>
                      <Popconfirm
                        title={t('common.deleteTitle')}
                        description={t('common.deleteContent')}
                        okText={t('common.confirm')}
                        cancelText={t('common.cancel')}
                        okButtonProps={{ loading: groupConfirmLoading }}
                        onConfirm={() => handleGroupDeleteConfirm(metricItem)}
                      >
                        <Button
                          type="link"
                          size="small"
                          disabled={
                            !!metricItem.child?.length || metricItem.is_pre
                          }
                          icon={<DeleteOutlined />}
                        ></Button>
                      </Popconfirm>
                    </Permission>
                  </div>
                }
              >
                <CustomTable
                  pagination={false}
                  dataSource={metricItem.child || []}
                  columns={columns}
                  rowKey="id"
                  rowDraggable={
                    canReorderCatalog &&
                    metricItem.child?.length > 1 &&
                    metricItem.child.every((item) => !item.is_pre)
                  }
                  onRowDragEnd={onRowDragEnd}
                />
                </Collapse>
              </div>
            ))
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </div>
      </Spin>
      {metricCount > 100 && (
        <div className="mt-[16px] flex justify-end">
          <Pagination
            current={metricPage}
            pageSize={100}
            showSizeChanger={false}
            total={metricCount}
            onChange={onMetricPageChange}
          />
        </div>
      )}
      <GroupModal
        ref={groupRef}
        monitorObject={+activeTab}
        pluginId={+pluginID}
        onSuccess={operateGroup}
      />
      <MetricModal
        ref={metricRef}
        monitorObject={+activeTab}
        pluginId={+pluginID}
        groupList={apiGroupList}
        onSuccess={operateMtric}
      />
    </div>
  );
};
export default Configure;
