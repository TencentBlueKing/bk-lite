'use client';
import React, {
  useState,
  useEffect,
  useRef,
  useImperativeHandle,
  forwardRef
} from 'react';
import { Select, Button, Tooltip, Input, Card, message } from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  CopyOutlined,
  BellOutlined,
  SaveOutlined,
  FolderOpenOutlined,
  ClearOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  CaretDownFilled,
  CaretRightFilled,
  DoubleLeftOutlined,
  MinusCircleOutlined,
  RightOutlined
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useConditionList } from '@/app/monitor/hooks';
import useMonitorApi from '@/app/monitor/api';
import useApiClient from '@/utils/request';
import { useSearchParams } from 'next/navigation';
import {
  ListItem,
  MetricItem,
  IndexViewItem,
  ObjectItem,
  GroupInfo
} from '@/app/monitor/types';
import {
  InstanceItem,
  QueryGroup,
  SearchPayload,
  QueryPanelRef,
  QueryPanelProps,
  SaveQueryModalRef,
  SavedQueryDrawerRef
} from '@/app/monitor/types/search';
import { cloneDeep } from 'lodash';
import SavedQueryDrawer from './savedQueryDrawer';
import SaveQueryModal from './saveQueryModal';

const { Option } = Select;

export type { QueryGroup, SearchPayload, QueryPanelRef, QueryPanelProps };

const generateId = () => crypto.randomUUID();

const generateGroupName = (index: number) => `查询条件 ${index + 1}`;

const QueryPanel = forwardRef<QueryPanelRef, QueryPanelProps>(
  ({ onSearch }, ref) => {
    const { t } = useTranslation();
    const { isLoading } = useApiClient();
    const searchParams = useSearchParams();
    const {
      getMonitorObject,
      getMonitorMetrics,
      getMetricsGroup,
      getInstanceList
    } = useMonitorApi();
    const CONDITION_LIST = useConditionList();
    const [panelCollapsed, setPanelCollapsed] = useState(false);
    const initialObjectId = searchParams.get('monitor_object');
    const initialInstanceId = searchParams.get('instance_id');
    const initialMetricId = searchParams.get('metric_id');
    const [queryGroups, setQueryGroups] = useState<QueryGroup[]>([
      {
        id: generateId(),
        name: '查询条件 1',
        object: '',
        instanceIds: [],
        metric: null,
        aggregation: 'AVG',
        conditions: [],
        collapsed: false
      }
    ]);
    const [activeGroupId, setActiveGroupId] = useState<string>(
      queryGroups[0].id
    );
    const [urlParamsApplied, setUrlParamsApplied] = useState(false);
    const [autoSearchTriggered, setAutoSearchTriggered] = useState(false);
    const [editingNameGroupId, setEditingNameGroupId] = useState<string | null>(
      null
    );
    const [objLoading, setObjLoading] = useState<boolean>(false);
    const [objects, setObjects] = useState<ObjectItem[]>([]);
    const [metricsMap, setMetricsMap] = useState<Record<string, MetricItem[]>>(
      {}
    );
    const [metricsGroupMap, setMetricsGroupMap] = useState<
      Record<string, IndexViewItem[]>
    >({});
    const [instancesMap, setInstancesMap] = useState<
      Record<string, InstanceItem[]>
    >({});
    const [labelsMap, setLabelsMap] = useState<Record<string, string[]>>({});
    const [metricsLoading, setMetricsLoading] = useState<
      Record<string, boolean>
    >({});
    const [instanceLoading, setInstanceLoading] = useState<
      Record<string, boolean>
    >({});
    const metricsAbortControllerRef = useRef<Record<string, AbortController>>(
      {}
    );
    const instanceAbortControllerRef = useRef<Record<string, AbortController>>(
      {}
    );
    const savedQueryDrawerRef = useRef<SavedQueryDrawerRef>(null);
    const saveQueryModalRef = useRef<SaveQueryModalRef>(null);
    const activeGroup =
      queryGroups.find((g) => g.id === activeGroupId) || queryGroups[0];
    const canSearch = () => {
      return queryGroups.some((g) => g.metric && g.instanceIds.length > 0);
    };

    const getSearchPayload = (): SearchPayload | null => {
      if (!canSearch()) return null;
      const objectsMap: Record<string, ObjectItem> = {};
      objects.forEach((obj) => {
        objectsMap[String(obj.id)] = obj;
      });
      return {
        queryGroups,
        activeGroup,
        metricsMap,
        instancesMap,
        objectsMap
      };
    };

    useImperativeHandle(ref, () => ({
      getSearchPayload,
      canSearch,
      getActiveGroup: () => activeGroup
    }));

    useEffect(() => {
      return () => {
        Object.values(metricsAbortControllerRef.current).forEach((c) =>
          c?.abort()
        );
        Object.values(instanceAbortControllerRef.current).forEach((c) =>
          c?.abort()
        );
      };
    }, []);

    useEffect(() => {
      if (isLoading) return;
      getObjects();
      // 应用 URL 参数到初始查询组
      if (
        !urlParamsApplied &&
        (initialObjectId || initialInstanceId || initialMetricId)
      ) {
        setQueryGroups((prev) => {
          const first = prev[0];
          if (!first) return prev;
          return [
            {
              ...first,
              object: initialObjectId ? +initialObjectId : first.object,
              instanceIds: initialInstanceId
                ? [initialInstanceId]
                : first.instanceIds,
              metric: initialMetricId || first.metric
            },
            ...prev.slice(1)
          ];
        });
        setUrlParamsApplied(true);
        if (initialObjectId) {
          getMetrics(+initialObjectId);
          getInstList(+initialObjectId);
        }
      }
    }, [
      isLoading,
      initialObjectId,
      initialInstanceId,
      initialMetricId,
      urlParamsApplied
    ]);

    useEffect(() => {
      if (!urlParamsApplied || autoSearchTriggered || !initialObjectId) return;
      const key = String(initialObjectId);
      const isDataReady =
        !metricsLoading[key] &&
        !instanceLoading[key] &&
        metricsMap[key] &&
        instancesMap[key];
      if (isDataReady && canSearch()) {
        setAutoSearchTriggered(true);
        handleSearch();
      }
    }, [
      urlParamsApplied,
      metricsMap,
      instancesMap,
      metricsLoading,
      instanceLoading,
      autoSearchTriggered,
      initialObjectId
    ]);

    const getObjects = async () => {
      try {
        setObjLoading(true);
        const data: ObjectItem[] = await getMonitorObject({
          add_instance_count: true
        });
        setObjects(data);
      } finally {
        setObjLoading(false);
      }
    };

    const getMetrics = async (objectId: React.Key): Promise<MetricItem[]> => {
      const key = String(objectId);
      metricsAbortControllerRef.current[key]?.abort();
      const abortController = new AbortController();
      metricsAbortControllerRef.current[key] = abortController;
      try {
        setMetricsLoading((prev) => ({ ...prev, [key]: true }));
        const config = { signal: abortController.signal };
        const params = { monitor_object_id: objectId };
        const [groupList, metricsList] = await Promise.all([
          getMetricsGroup(params, config),
          getMonitorMetrics(params, config)
        ]);
        const metricData = cloneDeep(metricsList || []);
        setMetricsMap((prev) => ({ ...prev, [key]: metricsList || [] }));
        const groupData = groupList.map((item: GroupInfo) => ({
          ...item,
          child: []
        }));
        metricData.forEach((metric: MetricItem) => {
          const target = groupData.find(
            (item: GroupInfo) => item.id === metric.metric_group
          );
          if (target) {
            target.child.push(metric);
          }
        });
        const filteredGroupData = groupData.filter(
          (item: IndexViewItem) => !!item.child?.length
        );
        setMetricsGroupMap((prev) => ({ ...prev, [key]: filteredGroupData }));
        return metricsList || [];
      } catch {
        return [];
      } finally {
        setMetricsLoading((prev) => ({ ...prev, [key]: false }));
      }
    };

    const getInstList = async (
      objectId: React.Key
    ): Promise<InstanceItem[]> => {
      const key = String(objectId);
      instanceAbortControllerRef.current[key]?.abort();
      const abortController = new AbortController();
      instanceAbortControllerRef.current[key] = abortController;
      try {
        setInstanceLoading((prev) => ({ ...prev, [key]: true }));
        const data = await getInstanceList(
          objectId,
          { page_size: -1 },
          { signal: abortController.signal }
        );
        const results = data.results || [];
        setInstancesMap((prev) => ({ ...prev, [key]: results }));
        return results;
      } catch {
        return [];
      } finally {
        setInstanceLoading((prev) => ({ ...prev, [key]: false }));
      }
    };

    const updateQueryGroup = (
      groupId: string,
      updates: Partial<QueryGroup>
    ) => {
      setQueryGroups((prev) =>
        prev.map((g) => (g.id === groupId ? { ...g, ...updates } : g))
      );
    };

    const addQueryGroup = () => {
      const newGroup: QueryGroup = {
        id: generateId(),
        name: generateGroupName(queryGroups.length),
        object: '',
        instanceIds: [],
        metric: null,
        aggregation: 'AVG',
        conditions: [],
        collapsed: false
      };
      setQueryGroups((prev) => [...prev, newGroup]);
      setActiveGroupId(newGroup.id);
    };

    const deleteQueryGroup = (groupId: string) => {
      if (queryGroups.length <= 1) return;
      setQueryGroups((prev) => {
        const filtered = prev.filter((g) => g.id !== groupId);
        return filtered.map((g, i) => ({ ...g, name: generateGroupName(i) }));
      });
      if (activeGroupId === groupId) {
        setActiveGroupId(
          queryGroups[0].id === groupId ? queryGroups[1]?.id : queryGroups[0].id
        );
      }
    };

    const duplicateQueryGroup = (groupId: string) => {
      const group = queryGroups.find((g) => g.id === groupId);
      if (!group) return;
      const newGroup: QueryGroup = {
        ...cloneDeep(group),
        id: generateId(),
        name: generateGroupName(queryGroups.length)
      };
      setQueryGroups((prev) => [...prev, newGroup]);
    };

    const toggleGroupCollapse = (groupId: string) => {
      updateQueryGroup(groupId, {
        collapsed: !queryGroups.find((g) => g.id === groupId)?.collapsed
      });
    };

    const toggleAllGroups = () => {
      const allCollapsed = queryGroups.every((g) => g.collapsed);
      setQueryGroups((prev) =>
        prev.map((g) => ({ ...g, collapsed: !allCollapsed }))
      );
    };

    const handleObjectChange = (groupId: string, objectId: React.Key) => {
      updateQueryGroup(groupId, {
        object: objectId,
        instanceIds: [],
        metric: null,
        conditions: []
      });
      if (objectId) {
        const key = String(objectId);
        if (!metricsMap[key]) {
          getMetrics(objectId);
        }
        if (!instancesMap[key]) {
          getInstList(objectId);
        }
      }
    };

    const handleMetricChange = (groupId: string, metricName: string) => {
      const group = queryGroups.find((g) => g.id === groupId);
      if (!group) return;
      const metrics = metricsMap[String(group.object)] || [];
      const target = metrics.find((item) => item.name === metricName);
      const labels = (target?.dimensions || []).map((item) => item.name);
      setLabelsMap((prev) => ({
        ...prev,
        [`${group.object}_${metricName}`]: labels
      }));
      updateQueryGroup(groupId, { metric: metricName, conditions: [] });
    };

    const handleLabelChange = (groupId: string, val: string, index: number) => {
      const group = queryGroups.find((g) => g.id === groupId);
      if (!group) return;
      const conditions = cloneDeep(group.conditions);
      conditions[index].label = val;
      updateQueryGroup(groupId, { conditions });
    };

    const handleConditionChange = (
      groupId: string,
      val: string,
      index: number
    ) => {
      const group = queryGroups.find((g) => g.id === groupId);
      if (!group) return;
      const conditions = cloneDeep(group.conditions);
      conditions[index].condition = val;
      updateQueryGroup(groupId, { conditions });
    };

    const handleValueChange = (
      groupId: string,
      e: React.ChangeEvent<HTMLInputElement>,
      index: number
    ) => {
      const group = queryGroups.find((g) => g.id === groupId);
      if (!group) return;
      const conditions = cloneDeep(group.conditions);
      conditions[index].value = e.target.value;
      updateQueryGroup(groupId, { conditions });
    };

    const addConditionItem = (groupId: string) => {
      const group = queryGroups.find((g) => g.id === groupId);
      if (!group) return;
      updateQueryGroup(groupId, {
        conditions: [
          ...group.conditions,
          { label: null, condition: null, value: '' }
        ]
      });
    };

    const deleteConditionItem = (groupId: string, index: number) => {
      const group = queryGroups.find((g) => g.id === groupId);
      if (!group) return;
      const conditions = cloneDeep(group.conditions);
      conditions.splice(index, 1);
      updateQueryGroup(groupId, { conditions });
    };

    const clearAll = () => {
      setQueryGroups([
        {
          id: generateId(),
          name: '查询条件 1',
          object: '',
          instanceIds: [],
          metric: null,
          aggregation: 'AVG',
          conditions: [],
          collapsed: false
        }
      ]);
    };

    const handleSearch = () => {
      const payload = getSearchPayload();
      if (payload) {
        onSearch(payload);
      }
    };

    const handleSaveQuery = () => {
      if (!canSearch()) {
        message.warning(t('monitor.search.noData'));
        return;
      }
      saveQueryModalRef.current?.showModal(queryGroups);
    };

    const handleOpenLoadDrawer = () => {
      savedQueryDrawerRef.current?.showDrawer();
    };

    const handleLoadSavedQuery = async (savedQueryGroups: QueryGroup[]) => {
      const objectIds = [
        ...new Set(savedQueryGroups.map((g) => g.object).filter(Boolean))
      ];
      const loadedMetricsMap: Record<string, MetricItem[]> = { ...metricsMap };
      const loadedInstancesMap: Record<string, InstanceItem[]> = {
        ...instancesMap
      };
      await Promise.all(
        objectIds.map(async (objectId) => {
          const key = String(objectId);
          const metricsPromise = metricsMap[key]
            ? Promise.resolve(metricsMap[key])
            : getMetrics(objectId);
          const instancesPromise = instancesMap[key]
            ? Promise.resolve(instancesMap[key])
            : getInstList(objectId);

          const [metrics, instances] = await Promise.all([
            metricsPromise,
            instancesPromise
          ]);
          loadedMetricsMap[key] = metrics;
          loadedInstancesMap[key] = instances;
        })
      );
      setQueryGroups(savedQueryGroups);
      const canSearchNow = savedQueryGroups.some(
        (g) => g.metric && g.instanceIds.length > 0
      );
      if (canSearchNow) {
        const objectsMap: Record<string, ObjectItem> = {};
        objects.forEach((obj) => {
          objectsMap[String(obj.id)] = obj;
        });
        const payload: SearchPayload = {
          queryGroups: savedQueryGroups,
          activeGroup: savedQueryGroups[0],
          metricsMap: loadedMetricsMap,
          instancesMap: loadedInstancesMap,
          objectsMap
        };
        onSearch(payload);
      }
    };

    const renderQueryGroup = (group: QueryGroup) => {
      const groupMetrics = metricsGroupMap[String(group.object)] || [];
      const groupInstances = instancesMap[String(group.object)] || [];
      const groupLabels = labelsMap[`${group.object}_${group.metric}`] || [];
      const isMetricsLoading = metricsLoading[String(group.object)] || false;
      const isInstanceLoading = instanceLoading[String(group.object)] || false;

      return (
        <Card
          key={group.id}
          size="small"
          className="mb-3"
          title={
            <div
              className="flex items-center gap-2 cursor-pointer"
              onClick={() => toggleGroupCollapse(group.id)}
            >
              {group.collapsed ? (
                <CaretRightFilled className="text-[var(--color-text-3)] text-xs" />
              ) : (
                <CaretDownFilled className="text-[var(--color-text-2)] text-xs" />
              )}
              {editingNameGroupId === group.id ? (
                <Input
                  size="small"
                  autoFocus
                  defaultValue={group.name}
                  className="w-[120px]"
                  onClick={(e) => e.stopPropagation()}
                  onBlur={(e) => {
                    const newName = e.target.value.trim() || group.name;
                    updateQueryGroup(group.id, { name: newName });
                    setEditingNameGroupId(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      const newName =
                        (e.target as HTMLInputElement).value.trim() ||
                        group.name;
                      updateQueryGroup(group.id, { name: newName });
                      setEditingNameGroupId(null);
                    }
                    if (e.key === 'Escape') {
                      setEditingNameGroupId(null);
                    }
                  }}
                />
              ) : (
                <span
                  className="font-medium text-[var(--color-text-1)] hover:text-[var(--color-primary)] cursor-text"
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditingNameGroupId(group.id);
                  }}
                >
                  {group.name}
                </span>
              )}
            </div>
          }
          extra={
            <div
              className="flex items-center"
              onClick={(e) => e.stopPropagation()}
            >
              <Tooltip title={t('monitor.events.createPolicy')}>
                <Button
                  type="text"
                  size="small"
                  icon={<BellOutlined />}
                  className="hidden text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
                  onClick={() => {
                    const objectInfo = objects.find(
                      (o) => o.id === group.object
                    );
                    const params = {
                      monitorName: objectInfo?.display_name || '',
                      monitorObjId: String(group.object),
                      instanceId: group.instanceIds[0] || '',
                      metricId: group.metric || '',
                      type: 'add'
                    };
                    const queryString = new URLSearchParams(params).toString();
                    window.open(
                      `/monitor/event/strategy/detail?${queryString}`,
                      '_blank',
                      'noopener,noreferrer'
                    );
                  }}
                />
              </Tooltip>
              <Tooltip title={t('common.copy')}>
                <Button
                  type="text"
                  size="small"
                  icon={<CopyOutlined />}
                  className="text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
                  onClick={() => duplicateQueryGroup(group.id)}
                />
              </Tooltip>
              {queryGroups.length > 1 && (
                <Tooltip title={t('common.delete')}>
                  <Button
                    type="text"
                    size="small"
                    icon={<DeleteOutlined />}
                    className="text-[var(--color-text-3)] hover:text-[var(--color-fail)]"
                    onClick={() => deleteQueryGroup(group.id)}
                  />
                </Tooltip>
              )}
            </div>
          }
          styles={{
            header: {
              cursor: 'pointer',
              backgroundColor: 'var(--color-fill-2)',
              borderRadius: '8px 8px 0 0'
            },
            body: group.collapsed
              ? { display: 'none' }
              : { backgroundColor: 'var(--color-bg-1)' }
          }}
        >
          <div className="space-y-4">
            {/* 对象选择 */}
            <div>
              <label className="text-xs font-medium text-[var(--color-text-3)] mb-[10px] block">
                {t('monitor.monitorObject')}
              </label>
              <Select
                className="w-full"
                placeholder={t('monitor.selectObject')}
                value={group.object || undefined}
                loading={objLoading}
                showSearch
                filterOption={(input, option) =>
                  String(option?.label || '')
                    .toLowerCase()
                    .includes(input.toLowerCase())
                }
                onChange={(val) => handleObjectChange(group.id, val)}
              >
                {objects.map((item) => (
                  <Option
                    key={item.id}
                    value={item.id}
                    label={item.display_name}
                  >
                    {item.display_name}
                  </Option>
                ))}
              </Select>
            </div>

            {/* 资产选择 */}
            <div>
              <label className="text-xs font-medium text-[var(--color-text-3)] mb-[10px] block">
                {t('monitor.source')}
              </label>
              <Select
                mode="multiple"
                className="w-full"
                placeholder={t('monitor.instance')}
                value={group.instanceIds}
                loading={isInstanceLoading}
                disabled={!group.object}
                maxTagCount="responsive"
                showSearch
                filterOption={(input, option) =>
                  String(option?.children || '')
                    .toLowerCase()
                    .includes(input.toLowerCase())
                }
                onChange={(val) =>
                  updateQueryGroup(group.id, { instanceIds: val })
                }
              >
                {groupInstances.map((item) => (
                  <Option key={item.instance_id} value={item.instance_id}>
                    {item.instance_name}
                  </Option>
                ))}
              </Select>
            </div>
            {/* 指标选择 */}
            <div>
              <label className="text-xs font-medium text-[var(--color-text-3)] mb-[10px] block">
                {t('monitor.metric')}
              </label>
              <Select
                className="w-full"
                placeholder={t('monitor.metric')}
                value={group.metric || undefined}
                loading={isMetricsLoading}
                disabled={!group.object}
                showSearch
                filterOption={(input, option) =>
                  String(option?.label || '')
                    .toLowerCase()
                    .includes(input.toLowerCase())
                }
                options={groupMetrics.map((item) => ({
                  label: item.display_name,
                  title: item.name,
                  options: (item.child || []).map((tex) => ({
                    label: tex.display_name,
                    value: tex.name
                  }))
                }))}
                onChange={(val) => handleMetricChange(group.id, val)}
              />
            </div>
            {/* 汇聚方法 */}
            <div>
              <label className="text-xs font-medium text-[var(--color-text-3)] mb-[10px] block">
                {t('monitor.aggregation')}
              </label>
              <Select
                className="w-full"
                value={group.aggregation}
                onChange={(val) =>
                  updateQueryGroup(group.id, { aggregation: val })
                }
              >
                <Option value="AVG">AVG</Option>
                <Option value="SUM">SUM</Option>
                <Option value="MAX">MAX</Option>
                <Option value="MIN">MIN</Option>
                <Option value="COUNT">COUNT</Option>
              </Select>
            </div>
            {/* 条件 */}
            <div>
              <label className="text-xs font-medium text-[var(--color-text-3)] mb-[10px] block">
                {t('monitor.filter')}
              </label>
              {group.conditions.length > 0 && (
                <div className="space-y-2 mb-3">
                  {group.conditions.map((conditionItem, index) => (
                    <div
                      key={index}
                      className="flex items-center gap-1.5 bg-[var(--color-fill-1)] rounded-md p-1.5"
                    >
                      <Select
                        className="w-20"
                        size="small"
                        placeholder={t('monitor.label')}
                        value={conditionItem.label}
                        showSearch
                        onChange={(val) =>
                          handleLabelChange(group.id, val, index)
                        }
                      >
                        {groupLabels.map((item) => (
                          <Option key={item} value={item}>
                            {item}
                          </Option>
                        ))}
                      </Select>
                      <Select
                        className="w-20"
                        size="small"
                        placeholder={t('monitor.term')}
                        value={conditionItem.condition}
                        onChange={(val) =>
                          handleConditionChange(group.id, val, index)
                        }
                      >
                        {CONDITION_LIST.map((item: ListItem) => (
                          <Option key={item.id} value={item.id}>
                            {item.name}
                          </Option>
                        ))}
                      </Select>
                      <Input
                        className="flex-1"
                        size="small"
                        placeholder={t('monitor.value')}
                        value={conditionItem.value}
                        onChange={(e) => handleValueChange(group.id, e, index)}
                      />
                      <Button
                        type="text"
                        size="small"
                        icon={<MinusCircleOutlined />}
                        className="text-[var(--color-text-3)] hover:text-[var(--color-fail)]"
                        onClick={() => deleteConditionItem(group.id, index)}
                      />
                    </div>
                  ))}
                </div>
              )}
              <Button
                type="link"
                size="small"
                disabled={!group.metric}
                className="p-0 m-0"
                onClick={() => addConditionItem(group.id)}
              >
                {t('monitor.addCondition')}
              </Button>
            </div>
          </div>
        </Card>
      );
    };

    return (
      <div className="relative h-full">
        {/* 左侧面板 */}
        <div
          className={`flex flex-col border-r transition-all duration-300 h-full ${
            panelCollapsed ? 'w-0 overflow-hidden' : 'w-[340px]'
          }`}
          style={{
            backgroundColor: 'var(--color-bg-1)',
            borderColor: 'var(--color-border-2)'
          }}
        >
          {/* 面板头部 */}
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ borderBottom: '1px solid var(--color-border-2)' }}
          >
            <span className="font-medium text-[var(--color-text-1)]">
              {t('monitor.search.dataQuery')}
            </span>
            <div className="flex items-center gap-0.5">
              <Tooltip
                title={
                  queryGroups.every((g) => g.collapsed)
                    ? t('common.expandAll')
                    : t('common.collapseAll')
                }
              >
                <Button
                  type="text"
                  size="small"
                  className="text-[var(--color-text-3)] hover:text-[var(--color-text-2)] hover:bg-[var(--color-bg-hover)]"
                  icon={
                    queryGroups.every((g) => g.collapsed) ? (
                      <MenuUnfoldOutlined />
                    ) : (
                      <MenuFoldOutlined />
                    )
                  }
                  onClick={toggleAllGroups}
                />
              </Tooltip>
              <Tooltip title={t('common.collapse')}>
                <Button
                  type="text"
                  size="small"
                  className="text-[var(--color-text-3)] hover:text-[var(--color-text-2)] hover:bg-[var(--color-bg-hover)]"
                  icon={<DoubleLeftOutlined />}
                  onClick={() => setPanelCollapsed(true)}
                />
              </Tooltip>
            </div>
          </div>
          {/* 查询组列表 */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {queryGroups.map(renderQueryGroup)}
            {/* 添加查询按钮 */}
            <Button
              type="dashed"
              icon={<PlusOutlined />}
              className="w-full"
              onClick={addQueryGroup}
            >
              {t('monitor.search.addQuery')}
            </Button>
          </div>
          {/* 面板底部 */}
          <div
            className="flex items-center gap-3 px-4 py-3"
            style={{ borderTop: '1px solid var(--color-border-2)' }}
          >
            <Button
              type="primary"
              disabled={!canSearch()}
              onClick={handleSearch}
              className="flex-1"
            >
              {t('common.search')}
            </Button>
            <span className="w-px h-5 bg-[var(--color-border-3)]" />
            <div className="flex items-center">
              <Tooltip title={t('monitor.search.saveQuery')}>
                <Button
                  type="text"
                  icon={<SaveOutlined />}
                  disabled={!canSearch()}
                  onClick={handleSaveQuery}
                />
              </Tooltip>
              <Tooltip title={t('monitor.search.loadSavedQuery')}>
                <Button
                  type="text"
                  icon={<FolderOpenOutlined />}
                  onClick={handleOpenLoadDrawer}
                />
              </Tooltip>
              <Tooltip title={t('monitor.search.clearQuery')}>
                <Button
                  type="text"
                  icon={<ClearOutlined />}
                  onClick={clearAll}
                />
              </Tooltip>
            </div>
          </div>
        </div>

        {/* 展开按钮 */}
        {panelCollapsed && (
          <Button
            type="text"
            icon={<RightOutlined />}
            className="absolute left-0 top-1/2 -translate-y-1/2 z-10 h-12 bg-[var(--color-bg-1)] shadow-md rounded-r-md border border-l-0 border-[var(--color-border-2)]"
            onClick={() => setPanelCollapsed(false)}
          />
        )}
        {/* 保存/加载查询组件 */}
        <SavedQueryDrawer
          ref={savedQueryDrawerRef}
          onLoad={handleLoadSavedQuery}
        />
        <SaveQueryModal ref={saveQueryModalRef} />
      </div>
    );
  }
);

QueryPanel.displayName = 'QueryPanel';

export default QueryPanel;
