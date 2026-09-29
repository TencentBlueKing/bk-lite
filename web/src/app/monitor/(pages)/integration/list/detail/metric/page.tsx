'use client';
import './register-metric-pilot';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { EditOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  Alert,
  Input,
  Button,
  Cascader,
  Popconfirm,
  message,
  Modal,
  Spin,
  Segmented,
  Select,
  Pagination,
  Tag,
  Tooltip
} from 'antd';
import useApiClient, { HandledRequestError } from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import { useCommon } from '@/app/monitor/context/common';
import metricStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import CompactEmptyState from '@/components/compact-empty-state';
import CustomTable from '@/components/custom-table';
import {
  ColumnItem,
  ModalRef,
  ObjectItem,
  MetricItem
} from '@/app/monitor/types';
import { MetricListItem, DimensionItem } from '@/app/monitor/types/integration';
import Collapse from '@/components/collapse';
import GroupModal from './groupModal';
import MetricModal from './metricModal';
import ObjectIcon from '@/app/monitor/components/objectIcon';
import { useRouter, useSearchParams } from 'next/navigation';
import Permission from '@/components/permission';
import {
  needsTagsEntry,
  getPluginFamilyObjects
} from '@/app/monitor/utils/monitorObject';
import { findCascaderPath } from '@/app/monitor/utils/common';
import { cloneDeep } from 'lodash';
import {
  buildIfmibMetricView,
  getDefaultMetricGroupOpenState,
  isIfmibMetric
} from './ifmibMetricView';
import { fetchAllMetricsGroups } from '@/app/monitor/api/fetchMetricCatalogPages';
import {
  CatalogMetricGroupOption,
  METRIC_BATCH_UPDATE_MAX_SIZE,
  buildUnitCascaderOptions,
  canonicalCatalogGroupId,
  catalogGroupLabel,
  dedupeCatalogMetricGroups,
  resolvePersistCatalogUnitId
} from '../configure/scriptMetricPersist';
import {
  consumeScriptMetricEditCarry,
  SCRIPT_METRIC_DRAFT_QUERY,
  ScriptMetricEditCarry
} from '../configure/scriptMetricEditCarry';
import {
  cleanMeasurementName,
  isSelfMetricName,
  visibleDimensionItems
} from '../configure/scriptMetricsParser';
import ScriptMetricGroupSelect from '../configure/scriptMetricGroupSelect';
import {
  MetricInlineDraft,
  MetricInlineItemError,
  applySuccessfulItemsToBaseline,
  chunkMetricBatchItems,
  collectDirtyBatchItems,
  countDirtyInlineFields,
  fieldErrorMessage,
  groupErrorsByMetricId,
  isInlineFieldDirty,
  isMetricInlineReadonly,
  parseMetricBatchUpdateErrors,
  snapshotMetricInlineDraft
} from './metricInlineEdit';

interface ObjectTabOption {
  label: React.ReactNode;
  value: string;
  title?: string;
}

const ObjectTabLabel = ({
  icon,
  name,
  isBase,
  baseLabel
}: {
  icon?: string;
  name: string;
  isBase: boolean;
  baseLabel: string;
}) => (
  <span className={metricStyle.objectChip}>
    <ObjectIcon icon={icon} size={16} />
    <span className={metricStyle.objectChipName}>{name}</span>
    {isBase ? (
      <span className={metricStyle.objectChipMark}>{baseLabel}</span>
    ) : null}
  </span>
);

const Configure = () => {
  const { isLoading } = useApiClient();
  const { getMonitorObject, getMetricsGroup, getMonitorMetrics } =
    useMonitorApi();
  const {
    updateMetricsGroup,
    updateMonitorMetrics,
    deleteMonitorMetrics,
    deleteMetricsGroup,
    batchUpdateMonitorMetrics
  } = useIntegrationApi();
  const { t } = useTranslation();
  const commonContext = useCommon();
  const unitOptions = useMemo(
    () => buildUnitCascaderOptions(commonContext?.groupedUnitList || []),
    [commonContext?.groupedUnitList]
  );
  const searchParams = useSearchParams();
  const router = useRouter();
  const groupName = searchParams.get('name') || '';
  const groupId = searchParams.get('id');
  const pluginID = searchParams.get('plugin_id') || '';
  const templateType = searchParams.get('template_type') || '';
  const enableIfmib = searchParams.get('enable_ifmib') !== 'false';
  const groupRef = useRef<ModalRef>(null);
  const metricRef = useRef<ModalRef>(null);
  const [searchText, setSearchText] = useState<string>('');
  const [nameInFilter, setNameInFilter] = useState<string>('');
  const batchMetricByIdRef = useRef<Map<number, MetricItem>>(new Map());
  const batchUncheckedIdsRef = useRef<Set<number>>(new Set());
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
  const [items, setItems] = useState<ObjectTabOption[]>([]);
  const [draggingItemId, setDraggingItemId] = useState<string | null>(null);
  const [dragOverTargetId, setDragOverTargetId] = useState<string | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [groupConfirmLoading, setGroupConfirmLoading] = useState(false);
  const [showTabs, setShowTabs] = useState<boolean>(false);
  const metricCatalogAbortRef = useRef<AbortController | null>(null);
  const scriptMetricDraftConsumedRef = useRef(false);
  const [catalogReady, setCatalogReady] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [batchEditing, setBatchEditing] = useState(false);
  const [batchSaving, setBatchSaving] = useState(false);
  const [inlineDrafts, setInlineDrafts] = useState<
    Record<number, MetricInlineDraft>
  >({});
  const [inlineBaseline, setInlineBaseline] = useState<
    Record<number, MetricInlineDraft>
  >({});
  const [inlineErrors, setInlineErrors] = useState<
    Record<number, MetricInlineItemError[]>
  >({});
  const [inlineGroups, setInlineGroups] = useState<CatalogMetricGroupOption[]>(
    []
  );
  const batchEditingRef = useRef(false);
  const canReorderCatalog =
    metricCount <= 100 &&
    !searchText.trim() &&
    !nameInFilter &&
    !batchEditing;

  useEffect(() => () => metricCatalogAbortRef.current?.abort(), []);

  const displayScriptMetricName = (name?: string) => {
    const raw = String(name || '').trim();
    if (!raw) {
      return '--';
    }
    if (templateType !== 'script' || isSelfMetricName(raw)) {
      return raw;
    }
    return cleanMeasurementName(raw) || raw;
  };

  const displayScriptDimensions = (dims?: DimensionItem[]) => {
    const source =
      templateType === 'script'
        ? visibleDimensionItems(dims || [])
        : dims || [];
    const names = source
      .map((item) => String(item?.name || '').trim())
      .filter(Boolean);
    return names.length ? names.join(',') : '--';
  };

  const mapGroupOptions = (
    groups: MetricListItem[]
  ): CatalogMetricGroupOption[] =>
    groups.map((item) => {
      const plugin = item.monitor_plugin;
      return {
        id: Number(item.id),
        name: item.name,
        display_name: item.display_name || item.name,
        monitor_plugin:
          typeof plugin === 'number' || typeof plugin === 'string'
            ? plugin
            : undefined,
        is_pre: item.is_pre
      };
    });

  const hydrateInlineDrafts = (metricItems: MetricItem[]) => {
    const nextDrafts: Record<number, MetricInlineDraft> = {};
    metricItems.forEach((metric) => {
      const id = Number(metric.id);
      if (!Number.isFinite(id) || id <= 0) {
        return;
      }
      nextDrafts[id] = snapshotMetricInlineDraft(metric);
    });
    setInlineDrafts(nextDrafts);
    setInlineBaseline(cloneDeep(nextDrafts));
    setInlineErrors({});
  };

  const exitBatchEditing = () => {
    batchEditingRef.current = false;
    setBatchEditing(false);
    setBatchSaving(false);
    setInlineDrafts({});
    setInlineBaseline({});
    setInlineErrors({});
  };

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
        const _items = getPluginFamilyObjects(groupName, data)
          .map((item: ObjectItem) => {
            const name = item.display_name || item.name;
            return {
              label: (
                <ObjectTabLabel
                  icon={item.icon}
                  name={name}
                  isBase={item.level === 'base'}
                  baseLabel={t('monitor.integrations.baseObject')}
                />
              ),
              value: String(item.id),
              title: name
            };
          });
        _objId = _items[0]?.value || '';
        setItems(_items);
      } else {
        setShowTabs(false);
        _objId = groupId || '';
      }
      setActiveTab(_objId);
      getInitData(_objId);
    } catch {
      setLoading(false);
      setCatalogReady(true);
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
    keyword = searchText.trim(),
    expandMetricNames: string[] = [],
    expandGroupIds: string[] = [],
    nameIn = nameInFilter
  ) => {
    const nameInNames = nameIn
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
    const metricParams = {
      monitor_object_id: +objId,
      monitor_plugin_id: +pluginID,
      // 后端 page_size 上限 100；本批超过一页时仍带 name_in 分页，并合并跨页勾选。
      ...(nameIn ? { name_in: nameIn } : {}),
      ...(keyword ? { keyword } : {})
    };
    const groupParams = {
      monitor_object_id: +objId,
      monitor_plugin_id: +pluginID
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
      setNameInFilter('');
      batchMetricByIdRef.current.clear();
      batchUncheckedIdsRef.current.clear();
    }
    try {
      // 厂商指标按页分页；IF-MIB 固定约十余条，单独拉全量后置底归并，避免拆页。
      const [groupCatalog, metricsPage, ifmibPage] = await Promise.all([
        fetchAllMetricsGroups(getMetricsGroup, groupParams, config),
        getMonitorMetrics(
          { ...metricParams, include_ifmib: false, page },
          config
        ),
        enableIfmib
          ? getMonitorMetrics(
            {
              ...metricParams,
              include_ifmib: true,
              is_ifmib: true,
              page: 1,
              page_size: 100
            },
            config
          )
          : Promise.resolve({ count: 0, items: [], metric_groups: [] })
      ]);
      if (abortController.signal.aborted) return;
      const pageMetrics = enableIfmib
        ? [...metricsPage.items, ...ifmibPage.items]
        : metricsPage.items;
      const { groups: dedupedGroups, idAlias } = dedupeCatalogMetricGroups(
        [
          ...(groupCatalog.items || []),
          ...(metricsPage.metric_groups || []),
          ...(enableIfmib ? ifmibPage.metric_groups || [] : [])
        ],
        {
          preferredPluginId: pluginID,
          preferredIds: pageMetrics.map((metric) => metric.metric_group)
        }
      );
      const rawGroupList: MetricListItem[] = dedupedGroups.map((group) => ({
        id: String(group.id),
        name: group.name || catalogGroupLabel(group),
        display_name: catalogGroupLabel(group),
        monitor_plugin: group.monitor_plugin ?? undefined,
        is_pre: group.is_pre === true,
        child: []
      }));
      setMetricCount(metricsPage.count);
      const catalogMetrics = pageMetrics.map((metric) => {
        const metricGroup = canonicalCatalogGroupId(metric.metric_group, idAlias);
        if (metricGroup == null || metricGroup === metric.metric_group) {
          return metric;
        }
        return { ...metric, metric_group: metricGroup };
      });
      const visibleGroupIds = new Set(
        catalogMetrics
          .filter((metric) => !isIfmibMetric(metric))
          .map((metric) => String(metric.metric_group))
      );
      setApiGroupList(
        rawGroupList.filter(
          (group) =>
            visibleGroupIds.has(String(group.id)) || group.is_pre === false
        )
      );
      const metricView = buildIfmibMetricView(
        rawGroupList,
        catalogMetrics,
        enableIfmib,
        (key) => t(key)
      );
      const defaultOpenState = getDefaultMetricGroupOpenState(metricView);
      const expandNameSet = new Set(
        [...expandMetricNames, ...nameInNames].filter(Boolean)
      );
      const matchesCarryName = (name?: string) => {
        const raw = String(name || '').trim();
        if (!raw) {
          return false;
        }
        if (expandNameSet.has(raw)) {
          return true;
        }
        const cleaned = cleanMeasurementName(raw);
        return Boolean(cleaned && expandNameSet.has(cleaned));
      };
      const expandGroupSet = new Set(expandGroupIds.filter(Boolean).map(String));
      if (expandNameSet.size) {
        const pageIds = new Set(
          catalogMetrics.map((metric) => Number(metric.id))
        );
        catalogMetrics.forEach((metric) => {
          if (matchesCarryName(metric.name) && metric.is_pre !== true) {
            batchMetricByIdRef.current.set(Number(metric.id), metric);
          }
        });
        const pageSelected = catalogMetrics
          .filter(
            (metric) =>
              matchesCarryName(metric.name) &&
              metric.is_pre !== true &&
              !batchUncheckedIdsRef.current.has(Number(metric.id))
          )
          .map((metric) => metric.id);
        setSelectedRowKeys((prev) => [
          ...prev.filter((id) => !pageIds.has(Number(id))),
          ...pageSelected
        ]);
      }
      const groupData = metricView.map((group) => {
        const expandByCarry =
          expandNameSet.size > 0 &&
          group.child.some((metric) => matchesCarryName(metric.name));
        const expandGroup = expandGroupSet.has(String(group.id));
        return {
          ...group,
          isOpen: expandGroup || expandByCarry
            ? true
            : currentOpenState
              ? (currentOpenState.get(group.id) ?? defaultOpenState.get(group.id) ?? false)
              : (defaultOpenState.get(group.id) ?? false)
        };
      });
      const flattened = groupData.flatMap((group) => group.child);
      setMetrics(flattened);
      setMetricData(groupData);
      setFilteredMetricData(groupData);
      if (batchEditingRef.current) {
        hydrateInlineDrafts(flattened);
        setInlineGroups(mapGroupOptions(rawGroupList));
      }
      return { count: metricsPage.count };
    } catch {
      if (!abortController.signal.aborted) {
        setMetricData([]);
        setFilteredMetricData([]);
      }
      return { count: 0 };
    } finally {
      if (metricCatalogAbortRef.current === abortController) {
        setLoading(false);
        setCatalogReady(true);
      }
    }
  };

  const onSearchTxtChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };

  const confirmIfDirtyThen = (action: () => void) => {
    const dirtyCount = countDirtyInlineFields(
      inlineDrafts,
      inlineBaseline,
      new Set(
        metrics
          .filter((item) => isMetricInlineReadonly(item))
          .map((item) => Number(item.id))
      )
    );
    if (!batchEditing || dirtyCount <= 0) {
      action();
      return;
    }
    Modal.confirm({
      title: t(
        'monitor.integrations.metricInlineEditUnsavedTitle',
        '有未保存的修改'
      ),
      content: t(
        'monitor.integrations.metricInlineEditUnsavedContent',
        '继续将丢弃未保存的修改，是否继续？'
      ),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: () => {
        exitBatchEditing();
        action();
      }
    });
  };

  const onTxtPressEnter = () => {
    confirmIfDirtyThen(() => {
      setMetricPage(1);
      getInitData(activeTab, true, 1, searchText.trim());
    });
  };

  const onTxtClear = () => {
    confirmIfDirtyThen(() => {
      setSearchText('');
      setMetricPage(1);
      getInitData(activeTab, true, 1, '');
    });
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

  const consumeScriptMetricDraftQuery = () => {
    const nextParams = new URLSearchParams(searchParams.toString());
    if (!nextParams.has(SCRIPT_METRIC_DRAFT_QUERY)) {
      return;
    }
    nextParams.delete(SCRIPT_METRIC_DRAFT_QUERY);
    const nextQuery = nextParams.toString();
    router.replace(
      nextQuery
        ? `/monitor/integration/list/detail/metric?${nextQuery}`
        : '/monitor/integration/list/detail/metric'
    );
  };

  const landScriptMetricCarry = async (carry: ScriptMetricEditCarry) => {
    const names = carry.metrics
      .map((item) => String(item?.name || '').trim())
      .filter(Boolean);
    if (!names.length) {
      return;
    }
    const targetObjectId = activeTab || groupId;
    if (!targetObjectId || !pluginID) {
      return;
    }
    const nameIn = names.join(',');
    batchMetricByIdRef.current.clear();
    batchUncheckedIdsRef.current.clear();
    setSelectedRowKeys([]);
    setSearchText('');
    setNameInFilter(nameIn);
    setMetricPage(1);
    const landed = await getInitData(
      String(targetObjectId),
      true,
      1,
      '',
      names,
      [],
      nameIn
    );
    const batchCount = landed?.count ?? 0;
    // 后端 max_page_size=100。第一页已勾选；本批更多页则继续拉取并入勾选与 ref。
    if (batchCount <= 100) {
      return;
    }
    try {
      const pageSize = 100;
      const pages = Math.ceil(batchCount / pageSize);
      const extraIds: React.Key[] = [];
      for (let page = 2; page <= pages; page += 1) {
        const extra = await getMonitorMetrics({
          monitor_object_id: +targetObjectId,
          monitor_plugin_id: +pluginID,
          name_in: nameIn,
          include_ifmib: false,
          page
        });
        (extra?.items || []).forEach((metric) => {
          if (metric.is_pre === true) {
            return;
          }
          const id = Number(metric.id);
          batchMetricByIdRef.current.set(id, metric);
          if (!batchUncheckedIdsRef.current.has(id)) {
            extraIds.push(metric.id);
          }
        });
      }
      if (extraIds.length) {
        setSelectedRowKeys((prev) => {
          const seen = new Set(prev.map((id) => Number(id)));
          return [
            ...prev,
            ...extraIds.filter((id) => !seen.has(Number(id)))
          ];
        });
      }
    } catch {
      // 后续页失败时保留已加载页的勾选。
    }
  };

  useEffect(() => {
    if (isLoading || loading || !catalogReady) {
      return;
    }
    if (scriptMetricDraftConsumedRef.current) {
      return;
    }
    if (searchParams.get(SCRIPT_METRIC_DRAFT_QUERY) !== '1') {
      return;
    }
    scriptMetricDraftConsumedRef.current = true;
    const carry =
      groupId && pluginID
        ? consumeScriptMetricEditCarry(groupId, pluginID)
        : null;
    consumeScriptMetricDraftQuery();
    if (!carry?.metrics.length) {
      return;
    }
    void landScriptMetricCarry(carry);
  }, [
    isLoading,
    loading,
    catalogReady,
    searchParams,
    groupId,
    pluginID
  ]);

  const operateGroup = () => {
    getInitData(activeTab, true);
  };

  const operateMtric = () => {
    getInitData(activeTab, true);
  };

  const onTabChange = (val: string | number) => {
    confirmIfDirtyThen(() => {
      const next = String(val);
      setMetricData([]);
      setActiveTab(next);
      setMetricPage(1);
      setSelectedRowKeys([]);
      setNameInFilter('');
      batchMetricByIdRef.current.clear();
      batchUncheckedIdsRef.current.clear();
      getInitData(next, false, 1);
    });
  };

  const onMetricPageChange = (page: number) => {
    confirmIfDirtyThen(() => {
      setMetricPage(page);
      getInitData(activeTab, true, page, searchText.trim());
    });
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
    setMetricData((prev) =>
      prev.map((item) => (item.id === id ? { ...item, isOpen } : item))
    );
    setFilteredMetricData((prev) =>
      prev.map((item) => (item.id === id ? { ...item, isOpen } : item))
    );
  };

  const allGroupsExpanded =
    filteredMetricData.length > 0 &&
    filteredMetricData.every((group) => group.isOpen);

  const batchFilterNames = useMemo(
    () =>
      nameInFilter
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
    [nameInFilter]
  );
  const readonlyMetricIds = useMemo(
    () =>
      new Set(
        metrics
          .filter((item) => isMetricInlineReadonly(item))
          .map((item) => Number(item.id))
      ),
    [metrics]
  );
  const dirtyFieldCount = countDirtyInlineFields(
    inlineDrafts,
    inlineBaseline,
    readonlyMetricIds
  );

  const popupContainer = () => document.body;

  const clearBatchFilter = () => {
    confirmIfDirtyThen(() => {
      batchMetricByIdRef.current.clear();
      batchUncheckedIdsRef.current.clear();
      setNameInFilter('');
      setMetricPage(1);
      getInitData(activeTab, true, 1, searchText.trim(), [], [], '');
    });
  };

  const enterBatchEditing = () => {
    batchEditingRef.current = true;
    setBatchEditing(true);
    hydrateInlineDrafts(metrics);
    setInlineGroups(mapGroupOptions(apiGroupList));
  };

  const patchInlineDraft = (
    metricId: number,
    field: keyof MetricInlineDraft,
    value: MetricInlineDraft[keyof MetricInlineDraft]
  ) => {
    setInlineDrafts((prev) => {
      const current = prev[metricId];
      if (!current) {
        return prev;
      }
      const nextDraft = { ...current, [field]: value };
      if (field === 'data_type' && value === 'Number' && current.data_type === 'Enum') {
        nextDraft.unit = 'none';
      }
      return { ...prev, [metricId]: nextDraft };
    });
    setInlineErrors((prev) => {
      if (!prev[metricId]) {
        return prev;
      }
      const remain = prev[metricId].filter((item) => item.field && item.field !== field);
      if (remain.length === prev[metricId].length) {
        return prev;
      }
      const next = { ...prev };
      if (remain.length) {
        next[metricId] = remain;
      } else {
        delete next[metricId];
      }
      return next;
    });
  };

  const handleBatchEditCancel = () => {
    confirmIfDirtyThen(() => {
      exitBatchEditing();
    });
  };

  const handleBatchEditSave = async () => {
    const items = collectDirtyBatchItems(
      inlineDrafts,
      inlineBaseline,
      readonlyMetricIds
    );
    if (!items.length) {
      message.warning(
        t('monitor.integrations.metricInlineEditEmpty', '没有需要保存的修改')
      );
      return;
    }
    const emptyName = items.find(
      (item) => item.display_name !== undefined && !String(item.display_name).trim()
    );
    if (emptyName) {
      setInlineErrors((prev) => ({
        ...prev,
        [emptyName.id]: [
          {
            id: emptyName.id,
            name: '',
            field: 'display_name',
            message: t('common.required'),
            code: 'validation'
          }
        ]
      }));
      return;
    }
    setBatchSaving(true);
    let updated = 0;
    let workingBaseline = inlineBaseline;
    const remaining = [...items];
    try {
      const chunks = chunkMetricBatchItems(remaining, METRIC_BATCH_UPDATE_MAX_SIZE);
      for (const chunk of chunks) {
        try {
          await batchUpdateMonitorMetrics({
            monitor_plugin: +pluginID,
            items: chunk
          });
          updated += chunk.length;
          const ids = chunk.map((item) => item.id);
          workingBaseline = applySuccessfulItemsToBaseline(
            workingBaseline,
            inlineDrafts,
            ids
          );
          setInlineBaseline(workingBaseline);
          setInlineErrors((prev) => {
            const next = { ...prev };
            ids.forEach((id) => {
              delete next[id];
            });
            return next;
          });
        } catch (error: unknown) {
          const parsed = parseMetricBatchUpdateErrors(error);
          const grouped = groupErrorsByMetricId(parsed);
          if (Object.keys(grouped).length) {
            setInlineErrors((prev) => ({ ...prev, ...grouped }));
          } else {
            const fallback =
              error instanceof HandledRequestError
                ? error.message
                : error instanceof Error
                  ? error.message
                  : t('common.operationFailed');
            const chunkErrors: Record<number, MetricInlineItemError[]> = {};
            chunk.forEach((item) => {
              chunkErrors[item.id] = [
                {
                  id: item.id,
                  name: '',
                  field: null,
                  message: fallback,
                  code: 'request_failed'
                }
              ];
            });
            setInlineErrors((prev) => ({ ...prev, ...chunkErrors }));
          }
          message.error(
            t(
              'monitor.integrations.metricBatchEditPartialFailed',
              '已更新 {updated} 个指标，{remaining} 个未更新',
              {
                updated,
                remaining: items.length - updated
              }
            )
          );
          return;
        }
      }
      message.success(
        t(
          'monitor.integrations.metricBatchEditSuccess',
          '已更新 {count} 个指标',
          { count: updated }
        )
      );
      exitBatchEditing();
      getInitData(activeTab, true);
    } finally {
      setBatchSaving(false);
    }
  };

  const dirtyCellClass = (record: MetricItem, field: keyof MetricInlineDraft) => {
    if (!batchEditing || isMetricInlineReadonly(record)) {
      return undefined;
    }
    const id = Number(record.id);
    return isInlineFieldDirty(inlineDrafts[id], inlineBaseline[id], field)
      ? 'bg-[var(--color-fill-2)]'
      : undefined;
  };

  const columns: ColumnItem[] = [
    {
      title: t('common.id'),
      dataIndex: 'name',
      width: 120,
      key: 'name',
      ellipsis: true,
      render: (value: string) => <>{displayScriptMetricName(value)}</>
    },
    {
      title: t('common.name'),
      dataIndex: 'display_name',
      width: 160,
      key: 'display_name',
      ellipsis: true,
      onCell: (record: MetricItem) => ({
        className: dirtyCellClass(record, 'display_name')
      }),
      render: (_, record) => {
        if (!batchEditing || isMetricInlineReadonly(record)) {
          return (
            <div className="flex items-center gap-1 overflow-hidden">
              <span className="truncate">
                {displayScriptMetricName(record.display_name || record.name)}
              </span>
            </div>
          );
        }
        const id = Number(record.id);
        const error = fieldErrorMessage(inlineErrors[id], 'display_name');
        return (
          <Input
            size="small"
            status={error ? 'error' : undefined}
            value={inlineDrafts[id]?.display_name ?? ''}
            onChange={(event) =>
              patchInlineDraft(id, 'display_name', event.target.value)
            }
            title={error || undefined}
          />
        );
      }
    },
    {
      title: t('monitor.integrations.dimension'),
      dataIndex: 'dimensions',
      width: 100,
      key: 'dimensions',
      ellipsis: true,
      render: (_, record) => <>{displayScriptDimensions(record.dimensions)}</>
    },
    {
      title: t('monitor.integrations.metricGroup'),
      dataIndex: 'metric_group',
      width: 160,
      key: 'metric_group',
      ellipsis: true,
      onCell: (record: MetricItem) => ({
        className: dirtyCellClass(record, 'metric_group')
      }),
      render: (_, record) => {
        if (!batchEditing) {
          return null;
        }
        if (isMetricInlineReadonly(record)) {
          const group = inlineGroups.find(
            (item) => Number(item.id) === Number(record.metric_group)
          );
          return <>{catalogGroupLabel(group) || '--'}</>;
        }
        const id = Number(record.id);
        const error = fieldErrorMessage(inlineErrors[id], 'metric_group');
        return (
          <ScriptMetricGroupSelect
            size="small"
            allowClear={false}
            className="w-full"
            objectId={activeTab}
            pluginId={pluginID}
            groups={inlineGroups}
            onGroupsChange={setInlineGroups}
            value={inlineDrafts[id]?.metric_group}
            getPopupContainer={popupContainer}
            popupMatchSelectWidth={false}
            onCreated={(created) => {
              setApiGroupList((prev) => {
                if (prev.some((item) => Number(item.id) === created.id)) {
                  return prev;
                }
                return [
                  ...prev,
                  {
                    id: String(created.id),
                    name: created.name || catalogGroupLabel(created),
                    display_name: catalogGroupLabel(created),
                    monitor_plugin: created.monitor_plugin ?? undefined,
                    is_pre: false,
                    child: []
                  }
                ];
              });
            }}
            onChange={(value) => {
              if (typeof value === 'number') {
                patchInlineDraft(id, 'metric_group', value);
              }
            }}
            placeholder={error || t('monitor.integrations.metricGroup')}
          />
        );
      }
    },
    {
      title: t('monitor.integrations.dataType'),
      dataIndex: 'data_type',
      key: 'data_type',
      width: 120,
      onCell: (record: MetricItem) => ({
        className: dirtyCellClass(record, 'data_type')
      }),
      render: (value: string, record: MetricItem) => {
        if (!batchEditing || isMetricInlineReadonly(record)) {
          return (
            <>
              {value === 'Enum'
                ? t('monitor.integrations.enum')
                : value === 'Number'
                  ? t('monitor.integrations.number')
                  : value}
            </>
          );
        }
        const id = Number(record.id);
        const error = fieldErrorMessage(inlineErrors[id], 'data_type');
        return (
          <Select
            size="small"
            className="w-full"
            status={error ? 'error' : undefined}
            value={inlineDrafts[id]?.data_type || 'Number'}
            getPopupContainer={popupContainer}
            popupClassName="[&_.ant-select-item-option-disabled]:pointer-events-auto"
            onChange={(next) => patchInlineDraft(id, 'data_type', next)}
          >
            <Select.Option value="Number">
              {t('monitor.integrations.number')}
            </Select.Option>
            <Select.Option value="Enum" disabled>
              <Tooltip
                title={t(
                  'monitor.integrations.metricInlineEditEnumDisabled',
                  '请用单条编辑配置映射'
                )}
              >
                <span className="block">
                  {t('monitor.integrations.enum')}
                </span>
              </Tooltip>
            </Select.Option>
          </Select>
        );
      }
    },
    {
      title: t('common.unit'),
      dataIndex: 'unit',
      width: 140,
      key: 'unit',
      onCell: (record: MetricItem) => ({
        className: dirtyCellClass(record, 'unit')
      }),
      render: (_, record) => {
        const draft = inlineDrafts[Number(record.id)];
        const dataType = batchEditing
          ? draft?.data_type || record.data_type
          : record.data_type;
        if (!batchEditing || isMetricInlineReadonly(record) || dataType === 'Enum') {
          return <>{dataType === 'Enum' ? '--' : record.unit || '--'}</>;
        }
        const id = Number(record.id);
        const error = fieldErrorMessage(inlineErrors[id], 'unit');
        const unitId = draft?.unit || '';
        const cascaderValue = unitId
          ? findCascaderPath(unitOptions as never, unitId)
          : [];
        return (
          <Cascader
            size="small"
            allowClear
            status={error ? 'error' : undefined}
            className="w-full"
            options={unitOptions}
            value={
              cascaderValue.length
                ? cascaderValue.map((item) => String(item))
                : undefined
            }
            getPopupContainer={popupContainer}
            displayRender={(labels) => {
              const leaf = labels[labels.length - 1];
              return leaf == null ? '' : String(leaf);
            }}
            onChange={(next) =>
              patchInlineDraft(id, 'unit', resolvePersistCatalogUnitId(next))
            }
            showSearch={{
              filter: (inputValue, path) => {
                const needle = inputValue.trim().toLowerCase();
                if (!needle) return true;
                return path.some((option) => {
                  const label = String(option.label ?? '').toLowerCase();
                  const extra = String(
                    (option as { searchText?: string }).searchText ?? ''
                  ).toLowerCase();
                  return label.includes(needle) || extra.includes(needle);
                });
              }
            }}
          />
        );
      }
    },
    {
      title: t('common.descripition'),
      dataIndex: 'display_description',
      key: 'display_description',
      width: 180,
      onCell: (record: MetricItem) => ({
        className: dirtyCellClass(record, 'description')
      }),
      render: (value: string, record: MetricItem) => {
        if (!batchEditing || isMetricInlineReadonly(record)) {
          return <>{value || '--'}</>;
        }
        const id = Number(record.id);
        const error = fieldErrorMessage(inlineErrors[id], 'description');
        return (
          <Input
            size="small"
            status={error ? 'error' : undefined}
            value={inlineDrafts[id]?.description ?? ''}
            onChange={(event) =>
              patchInlineDraft(id, 'description', event.target.value)
            }
            title={error || undefined}
          />
        );
      }
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      fixed: 'right',
      width: 110,
      render: (_, record) => {
        if (batchEditing) {
          return <span className="text-[var(--color-text-4)]">--</span>;
        }
        return record.is_pre ? (
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
        );
      }
    }
  ];
  const tableColumns = batchEditing
    ? columns
    : columns.filter((column) => column.key !== 'metric_group');

  const handleGroupSelectChange = (
    groupMetricIds: number[],
    keys: React.Key[]
  ) => {
    const groupIdSet = new Set(groupMetricIds);
    const selectedNow = new Set(keys.map((id) => Number(id)));
    if (nameInFilter) {
      groupMetricIds.forEach((id) => {
        if (selectedNow.has(id)) {
          batchUncheckedIdsRef.current.delete(id);
        } else {
          batchUncheckedIdsRef.current.add(id);
        }
      });
    }
    setSelectedRowKeys((prev) => [
      ...prev.filter((id) => !groupIdSet.has(Number(id))),
      ...keys
    ]);
  };

  const setAllGroupsOpen = (isOpen: boolean) => {
    const next = (groups: MetricListItem[]) =>
      groups.map((group) => ({ ...group, isOpen }));
    setMetricData(next);
    setFilteredMetricData(next);
  };

  return (
    <div className={metricStyle.metric}>
      {showTabs && (
        <Segmented
          className={metricStyle.objectSegmented}
          value={activeTab}
          options={items}
          onChange={onTabChange}
        />
      )}
      <p className="mb-[10px] text-[var(--color-text-2)]">
        {t('monitor.integrations.metricTitle')}
      </p>
      <div className="flex items-center justify-between mb-[15px]">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {batchFilterNames.length > 0 ? (
            <Tag
              color="blue"
              closable
              onClose={(e) => {
                e.preventDefault();
                clearBatchFilter();
              }}
            >
              {t(
                'monitor.integrations.batchMetricFilter',
                '仅显示本批 {count} 个',
                { count: batchFilterNames.length }
              )}
            </Tag>
          ) : null}
          <Input
            className="w-[400px]"
            placeholder={t('monitor.integrations.searchMetricPlaceholder')}
            value={searchText}
            allowClear
            onChange={onSearchTxtChange}
            onPressEnter={onTxtPressEnter}
            onClear={onTxtClear}
          />
        </div>
        <div>
          <Button
            className="mr-[8px]"
            disabled={!filteredMetricData.length}
            onClick={() => setAllGroupsOpen(!allGroupsExpanded)}
          >
            {allGroupsExpanded
              ? t('common.collapseAll')
              : t('common.expandAll')}
          </Button>
          <Permission requiredPermissions={['Add Group']} className="mr-[8px]">
            <Button
              type="primary"
              disabled={batchEditing}
              onClick={() => openGroupModal('add')}
            >
              {t('monitor.integrations.addGroup')}
            </Button>
          </Permission>
          {batchEditing ? (
            <>
              <Button
                type="primary"
                className="mr-[8px]"
                loading={batchSaving}
                disabled={dirtyFieldCount <= 0}
                onClick={() => void handleBatchEditSave()}
              >
                {t(
                  'monitor.integrations.metricInlineEditSave',
                  '保存（{count} 处修改）',
                  { count: dirtyFieldCount }
                )}
              </Button>
              <Button
                className="mr-[8px]"
                disabled={batchSaving}
                onClick={handleBatchEditCancel}
              >
                {t('common.cancel')}
              </Button>
            </>
          ) : (
            <Permission requiredPermissions={['Edit Metric']} className="mr-[8px]">
              <Button onClick={enterBatchEditing}>
                {t('common.batchEdit')}
              </Button>
            </Permission>
          )}
          <Permission requiredPermissions={['Add Metric']}>
            <Button
              disabled={batchEditing}
              onClick={() => openMetricModal('add')}
            >
              {t('monitor.integrations.addMetric')}
            </Button>
          </Permission>
        </div>
      </div>
      <Spin spinning={loading}>
        <div
          className={metricStyle.metricTable}
          style={{
            height: showTabs ? 'calc(100vh - 396px)' : 'calc(100vh - 346px)'
          }}
        >
          {batchFilterNames.length > 0 ? (
            <Alert
              type="info"
              showIcon
              className="mb-[10px]"
              message={
                <div className="flex items-center justify-between gap-3">
                  <span>
                    {t(
                      'monitor.integrations.batchMetricFilterBanner',
                      '仅显示本批 {count} 个指标，其他指标（含自监控）已隐藏',
                      { count: batchFilterNames.length }
                    )}
                  </span>
                  <Button
                    type="link"
                    className="h-auto p-0"
                    onClick={clearBatchFilter}
                  >
                    {t(
                      'monitor.integrations.batchMetricFilterShowAll',
                      '查看全部'
                    )}
                  </Button>
                </div>
              }
            />
          ) : null}
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
                sortable={!metricItem.is_pre && canReorderCatalog && !batchEditing}
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
                        disabled={metricItem.is_pre || batchEditing}
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
                            batchEditing ||
                            !!metricItem.child?.length ||
                            metricItem.is_pre
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
                  columns={tableColumns}
                  rowKey="id"
                  rowSelection={{
                    selectedRowKeys,
                    onChange: (keys) =>
                      handleGroupSelectChange(
                        (metricItem.child || []).map((item) => Number(item.id)),
                        keys
                      ),
                    getCheckboxProps: (record: MetricItem) => ({
                      disabled: record.is_pre === true
                    })
                  }}
                  rowDraggable={
                    !batchEditing &&
                    canReorderCatalog &&
                    metricItem.child?.length > 1 &&
                    metricItem.child.every((item) => !item.is_pre)
                  }
                  rowClassName={(record: MetricItem) =>
                    batchEditing && isMetricInlineReadonly(record)
                      ? 'bg-[var(--color-fill-1)] text-[var(--color-text-4)]'
                      : ''
                  }
                  onRowDragEnd={onRowDragEnd}
                />
                </Collapse>
              </div>
            ))
          ) : (
            <CompactEmptyState description={t('common.noData')} />
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
        catalogMetrics={metrics}
        onGroupListChange={(created) => {
          const groupId = created?.id != null ? String(created.id) : '';
          void getInitData(
            activeTab,
            true,
            metricPage,
            searchText.trim(),
            [],
            groupId ? [groupId] : []
          );
        }}
        onSuccess={operateMtric}
      />
    </div>
  );
};
export default Configure;
