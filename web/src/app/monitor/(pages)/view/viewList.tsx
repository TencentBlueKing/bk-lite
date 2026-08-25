'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Input, Button, Select, message } from 'antd';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import { useTranslation } from '@/utils/i18n';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import { useRouter, useSearchParams } from 'next/navigation';
import ViewModal from './viewModal';
import {
  ColumnItem,
  ModalRef,
  Pagination,
  TableDataItem,
  IntegrationItem,
  ObjectItem,
  MetricItem
} from '@/app/monitor/types';
import { ViewListProps, ViewPluginOption } from '@/app/monitor/types/view';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { ListItem } from '@/types';
import { OBJECT_DEFAULT_ICON } from '@/app/monitor/constants';
import { getProfessionalDashboardUrl } from '@/app/monitor/dashboards/registry';
import { withDashboardReturnContext } from '@/app/monitor/dashboards/shared/utils';
import { encodeInstanceIdValuesParam } from '@/app/monitor/dashboards/shared/utils/instance';
import {
  getBaseObject,
  getDerivativeObjectNames
} from '@/app/monitor/utils/monitorObject';
import { findByMonitorId, sameMonitorId } from '@/app/monitor/utils/monitorIds';
import {
  DEFAULT_VIEW_FIXED_FIELD_KEYS,
  resolveViewColumns
} from './viewColumnPreference';
import {
  INSTANCE_VIEW_ACTION_KEY,
  RESOURCE_IP_ROLE,
  buildInstanceViewColumns,
  buildReportTimeColumn,
  buildReportingStatusColumn,
  displayFieldKey,
  displayFieldParamKey
} from './instanceViewColumns';
const { Option } = Select;

const ViewList: React.FC<ViewListProps> = ({
  objects,
  objectId,
  showTab,
  updateTree
}) => {
  const { isLoading } = useApiClient();
  const { getMonitorMetrics, getInstanceList, getEffectivePlugins } =
    useMonitorApi();
  const {
    getInstanceSearch,
    getInstanceQueryParams,
    getViewColumnPreference,
    saveViewColumnPreference
  } = useViewApi();
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getEnumValueUnit } = useUnitTransform();
  const viewRef = useRef<ModalRef>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef<number>(0);
  const columnAbortControllerRef = useRef<AbortController | null>(null);
  const columnRequestIdRef = useRef<number>(0);
  const currentObjectIdRef = useRef<React.Key>(objectId);
  const colonyRef = useRef<string[]>([]);
  const nodeRef = useRef<string | null>(null);
  const columnFiltersRef = useRef<Record<string, string[]>>({});
  const searchTextRef = useRef('');
  const paginationRef = useRef<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  });
  const [searchText, setSearchText] = useState<string>('');
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  });
  const [frequence, setFrequence] = useState<number>(0);
  const [plugins, setPlugins] = useState<ViewPluginOption[]>([]);
  const columns: ColumnItem[] = [
    buildReportTimeColumn({ t, convertToLocalizedTime }),
    buildReportingStatusColumn({ t, includeFilters: true }),
    {
      title: t('common.action'),
      key: INSTANCE_VIEW_ACTION_KEY,
      dataIndex: INSTANCE_VIEW_ACTION_KEY,
      width: 180,
      fixed: 'right',
      render: (_, record) => (
        <>
          <Button
            className="mr-[10px]"
            type="link"
            onClick={() => openViewModal(record)}
          >
            {t('common.detail')}
          </Button>
          <Button type="link" onClick={() => linkToDetial(record)}>
            {t('monitor.views.dashboard')}
          </Button>
        </>
      )
    }
  ];
  const [tableColumn, setTableColumn] = useState<ColumnItem[]>(columns);
  const [columnPreference, setColumnPreference] = useState<string[] | null>(
    null
  );
  const [fixedColumnPreference, setFixedColumnPreference] = useState<
    string[] | null
  >(null);
  const [metrics, setMetrics] = useState<MetricItem[]>([]);
  const [node, setNode] = useState<string | null>(null);
  const [colony, setColony] = useState<string[]>([]);
  const [columnFilters, setColumnFilters] = useState<Record<string, string[]>>(
    {}
  );
  const [ipFilterOptions, setIpFilterOptions] = useState<string[]>([]);
  // 字段展示列（云平台子对象 IP）的候选取值，来源与 asset.ip 的候选值互相独立。
  const [fieldFilterOptions, setFieldFilterOptions] = useState<
    Record<string, string[]>
  >({});
  const [queryData, setQueryData] = useState<any[]>([]);
  const [nodeList, setNodeList] = useState<ListItem[]>([]);

  // 异步列加载收尾可能晚于 colony 更新；请求参数一律读 ref，避免跳转过滤被空闭包冲掉。
  useEffect(() => {
    colonyRef.current = colony;
  }, [colony]);
  useEffect(() => {
    nodeRef.current = node;
  }, [node]);
  useEffect(() => {
    columnFiltersRef.current = columnFilters;
  }, [columnFilters]);
  useEffect(() => {
    searchTextRef.current = searchText;
  }, [searchText]);
  useEffect(() => {
    paginationRef.current = pagination;
  }, [pagination]);

  const sameStringArray = (left: string[], right: string[]) =>
    left.length === right.length && left.every((item) => right.includes(item));

  const resolveProcessHostFilterIds = (
    rawIds: string[],
    hostOptions: Array<{ id?: string; name?: string }>
  ) => {
    if (!rawIds.length) return rawIds;
    if (!hostOptions.length) return rawIds;
    const byId = new Map(
      hostOptions
        .filter((item) => item?.id != null && item.id !== '')
        .map((item) => [String(item.id), String(item.id)])
    );
    const byName = new Map(
      hostOptions
        .filter((item) => item?.name != null && item.name !== '' && item?.id != null)
        .map((item) => [String(item.name), String(item.id)])
    );
    return rawIds.map((raw) => byId.get(raw) || byName.get(raw) || raw);
  };

  const currentObjectName = useMemo(() => {
    return findByMonitorId(objects, objectId)?.name || '';
  }, [objects, objectId]);

  const instNamePlaceholder = useMemo(() => {
    const current = findByMonitorId(objects, objectId);
    const baseTarget = current ? getBaseObject(current, objects) : undefined;
    const title: string = baseTarget?.display_name || t('monitor.source');
    return title;
  }, [objects, objectId, t]);

  const isPod = useMemo(() => {
    return currentObjectName === 'Pod';
  }, [currentObjectName]);

  const isNode = useMemo(() => {
    return currentObjectName === 'Node';
  }, [currentObjectName]);

  const isProcess = useMemo(() => {
    return currentObjectName === 'Process';
  }, [currentObjectName]);

  const needsAssetIpFilter = useMemo(() => {
    const summaryColumns =
      findByMonitorId(objects, objectId)?.instance_summary_columns ||
      [];
    return summaryColumns.some((column) => column.fact === 'asset.ip');
  }, [objects, objectId]);

  // 云平台子对象的内置 IP 列（role=resource_ip）：候选值需要后端下发，走同一个枚举接口。
  const roleFieldColumns = useMemo(() => {
    return (findByMonitorId(objects, objectId)?.display_fields || []).filter(
      (column) => column.type === 'field' && column.role === RESOURCE_IP_ROLE
    );
  }, [objects, objectId]);

  const showMultipleConditions = useMemo(() => {
    const derivativeNames = getDerivativeObjectNames(objects).filter(
      (name) => !['Pod', 'Node'].includes(name)
    );
    return (
      derivativeNames.includes(currentObjectName) || showTab || isProcess
    );
  }, [objects, currentObjectName, showTab, isProcess]);

  // 顶栏只放「列头没有」的维度：Pod 节点；Process 主机已迁到列头；其它非 K8S 衍生对象仍用顶栏集群。
  const showTopFilterBar = useMemo(() => {
    if (isProcess) return false;
    if (showTab && isPod) return true;
    if (showTab && isNode) return false;
    return showMultipleConditions && !showTab;
  }, [isProcess, showTab, isPod, isNode, showMultipleConditions]);

  const resolvedColumns = useMemo(
    () =>
      resolveViewColumns(
        tableColumn,
        columnPreference,
        ['action'],
        fixedColumnPreference,
        DEFAULT_VIEW_FIXED_FIELD_KEYS
      ),
    [tableColumn, columnPreference, fixedColumnPreference]
  );

  // 动态处理进度条列宽度；列头过滤的 filteredValue 与状态同步（服务端过滤）。
  const displayColumns = useMemo(() => {
    const mergedIpOptions = Array.from(
      new Set(
        [
          ...ipFilterOptions,
          ...(columnFilters['asset.ip'] || []),
          ...tableData.flatMap((row) => {
            const facts = row?.summary_facts as
              | Record<string, unknown>
              | undefined;
            const factIp = facts?.['asset.ip'];
            const fallbackIp = row?.ip;
            return [factIp, fallbackIp]
              .filter((item) => item != null && item !== '')
              .map((item) => String(item).trim());
          })
        ].filter(Boolean)
      )
    ).sort();
    const assetIpFilters = mergedIpOptions.map((ip) => ({
      text: ip,
      value: ip
    }));

    // 字段展示列候选值：后端下发 + 当前页取值 + 已选值，与 asset.ip 的合并方式一致。
    const fieldFilters: Record<string, { text: string; value: string }[]> = {};
    roleFieldColumns.forEach((column) => {
      const binding = column.metrics?.[0];
      const paramKey = displayFieldParamKey(binding?.field);
      const dataKey = displayFieldKey(
        binding?.plugin,
        binding?.metric,
        binding?.field
      );
      const pageValues = tableData
        .map((row) => row?.[dataKey])
        .filter((value) => value != null && value !== '')
        .map((value) => String(value).trim());
      fieldFilters[paramKey] = Array.from(
        new Set(
          [
            ...(fieldFilterOptions[paramKey] || []),
            ...(columnFilters[paramKey] || []),
            ...pageValues
          ].filter(Boolean)
        )
      )
        .sort()
        .map((value) => ({ text: value, value }));
    });

    return resolvedColumns.columns.map((col: ColumnItem) => {
      let next: ColumnItem = col;
      if (col.type === 'progress') {
        next = {
          ...next,
          width: tableData.length > 0 ? 300 : undefined
        };
      }
      if (col.key === 'base_instance_name') {
        next = {
          ...next,
          filterMultiple: true,
          filterSearch: true,
          filteredValue: colony.length ? colony : null
        };
      }
      if (String(col.key) === 'summary_fact:asset.ip') {
        next = {
          ...next,
          filterMultiple: true,
          filterSearch: true,
          filterParam: 'asset.ip',
          filters: assetIpFilters.length ? assetIpFilters : undefined
        };
      }
      if (col.role === RESOURCE_IP_ROLE) {
        const options = fieldFilters[String(col.filterParam)] || [];
        next = {
          ...next,
          filters: options.length ? options : undefined
        };
      }
      const filterParam = next.filterParam as string | undefined;
      if (filterParam) {
        const selected = columnFilters[filterParam] || [];
        next = {
          ...next,
          filteredValue: selected.length ? selected : null
        };
      }
      return next;
    });
  }, [
    resolvedColumns.columns,
    tableData,
    colony,
    columnFilters,
    ipFilterOptions,
    fieldFilterOptions,
    roleFieldColumns
  ]);

  const fieldGroups = useMemo(() => {
    const metricKeys = new Set(
      (findByMonitorId(objects, objectId)?.display_fields || []).map(
        (field) => field.column_key
      )
    );
    const choosableFields = tableColumn.filter((column) => column.key !== 'action');
    return {
      choosableFields,
      groups: [
        {
          title: t('monitor.events.basicInformation'),
          key: 'baseInfo',
          child: choosableFields.filter((column) => !metricKeys.has(column.key))
        },
        {
          title: t('monitor.events.metricInformation'),
          key: 'metricInfo',
          child: choosableFields.filter((column) => metricKeys.has(column.key))
        }
      ].filter((group) => group.child.length > 0)
    };
  }, [objectId, objects, tableColumn, t]);

  useEffect(() => {
    if (isLoading) return;
    if (objectId && objects?.length) {
      currentObjectIdRef.current = objectId;
      cancelAllRequests();
      setColumnPreference(null);
      setFixedColumnPreference(null);
      setTableColumn(columns);
      setTableData([]);
      setPagination((prev: Pagination) => ({
        ...prev,
        current: 1
      }));
      const hostFromUrl =
        findByMonitorId(objects, objectId)?.name === 'Process'
          ? searchParams.get('vm_params.instance_id')
          : null;
      const nextColony = hostFromUrl ? [hostFromUrl] : [];
      setNode(null);
      nodeRef.current = null;
      setColony(nextColony);
      colonyRef.current = nextColony;
      setColumnFilters({});
      columnFiltersRef.current = {};
      setIpFilterOptions([]);
      setFieldFilterOptions({});
      getColoumnAndData();
    }
    // searchParams host 过滤变更时也要重载（同对象再次跳转）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    objectId,
    objects,
    isLoading,
    searchParams.get('vm_params.instance_id')
  ]);

  useEffect(() => {
    if (objectId && objects?.length && !isLoading) {
      onRefresh();
    }
  }, [pagination.current, pagination.pageSize]);

  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      getAssetInsts(objectId, 'timer');
    }, frequence);
    return () => {
      clearTimer();
    };
  }, [
    frequence,
    objectId,
    pagination.current,
    pagination.pageSize,
    searchText
  ]);

  // 条件过滤请求
  useEffect(() => {
    if (objectId && objects?.length && !isLoading) {
      onRefresh();
    }
  }, [colony, node, columnFilters]);

  // 组件卸载时取消未完成的请求
  useEffect(() => {
    return () => {
      cancelAllRequests();
    };
  }, []);

  const cancelAllRequests = () => {
    abortControllerRef.current?.abort();
    columnAbortControllerRef.current?.abort();
  };

  const updatePage = () => {
    onRefresh();
    updateTree?.();
  };

  const getParams = () => {
    // field:* 可能含逗号拼接的多 IP，必须传数组，不能 join(',')，否则后端拆开后无法精确匹配。
    const vm_params: Record<string, string | string[]> = {
      instance_id: colonyRef.current.join(','),
      node: nodeRef.current || ''
    };
    Object.entries(columnFiltersRef.current).forEach(([key, values]) => {
      if (!values?.length) {
        return;
      }
      vm_params[key] = key.startsWith('field:') ? [...values] : values.join(',');
    });
    return {
      page: paginationRef.current.current,
      page_size: paginationRef.current.pageSize,
      add_metrics: true,
      name: searchTextRef.current,
      vm_params
    };
  };

  const getColoumnAndData = async () => {
    // 取消上一次未完成的列相关请求
    columnAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    columnAbortControllerRef.current = abortController;
    const currentRequestId = ++columnRequestIdRef.current;
    const objParams = {
      monitor_object_id: String(objectId)
    };
    const targetObject = findByMonitorId(objects, objectId);
    const objName = targetObject?.name;
    const config = { signal: abortController.signal };
    const displayMetricNames = (targetObject?.display_fields || [])
      .flatMap((column) => column.metrics || [])
      .map((binding) => binding.metric)
      .filter(Boolean);
    const getMetrics = getMonitorMetrics(
      {
        ...objParams,
        ...(displayMetricNames.length
          ? { name_in: [...new Set(displayMetricNames)].join(',') }
          : {})
      },
      config
    );
    const shouldFetchQueryParams =
      showMultipleConditions || needsAssetIpFilter || roleFieldColumns.length > 0;
    setTableLoading(true);
    try {
      const res = await Promise.all([
        getMetrics,
        shouldFetchQueryParams &&
          getInstanceQueryParams(objName as string, objParams, config),
        getViewColumnPreference(objectId, config).catch(() => null)
      ]);
      // 检查是否是最新的请求
      if (currentRequestId !== columnRequestIdRef.current) {
        return;
      }
      const k8sQuery = res[1];
      setColumnPreference(res[2]?.field_keys || null);
      setFixedColumnPreference(
        res[2] == null
          ? null
          : Array.isArray(res[2].fixed_field_keys)
            ? res[2].fixed_field_keys
            : null
      );
      let queryForm: any[] = [];
      if (k8sQuery?.cluster) {
        queryForm = k8sQuery?.cluster || [];
        setNodeList(k8sQuery?.node || []);
      } else if (Array.isArray(k8sQuery) || Array.isArray(k8sQuery?.items)) {
        const parentEnum = Array.isArray(k8sQuery)
          ? k8sQuery
          : k8sQuery.items;
        queryForm = parentEnum.map((item: any) => {
          if (typeof item === 'string') {
            return { id: item, child: [] };
          }
          return {
            id: item?.id,
            name: item?.name || '',
            child: []
          };
        });
      } else {
        queryForm = [];
      }
      const nextIpOptions = Array.isArray(k8sQuery?.asset_ips)
        ? k8sQuery.asset_ips
          .map((ip: unknown) => String(ip || '').trim())
          .filter(Boolean)
        : [];
      setIpFilterOptions(nextIpOptions);
      const rawFieldOptions = k8sQuery?.field_options;
      const nextFieldOptions: Record<string, string[]> = {};
      if (rawFieldOptions && typeof rawFieldOptions === 'object') {
        Object.entries(rawFieldOptions).forEach(([key, values]) => {
          nextFieldOptions[key] = Array.isArray(values)
            ? values.map((value) => String(value || '').trim()).filter(Boolean)
            : [];
        });
      }
      setFieldFilterOptions(nextFieldOptions);
      setQueryData(queryForm);
      if (objName === 'Process' && colonyRef.current.length) {
        const resolved = resolveProcessHostFilterIds(
          colonyRef.current,
          queryForm
        );
        if (!sameStringArray(resolved, colonyRef.current)) {
          colonyRef.current = resolved;
          setColony(resolved);
        }
      }
      setMetrics(res[0].items);
      if (objName) {
        const actionColumn = columns.find(
          (column) => column.key === INSTANCE_VIEW_ACTION_KEY
        );
        setTableColumn([
          ...buildInstanceViewColumns({
            objects,
            targetObject,
            t,
            convertToLocalizedTime,
            metrics: res[0].items,
            getEnumValueUnit,
            objectId,
            queryData: queryForm,
            ipFilterOptions: nextIpOptions,
            fieldFilterOptions: nextFieldOptions,
            includeStatusFilters: true,
            includeDimensionTooltip: true
          }),
          ...(actionColumn ? [actionColumn] : [])
        ]);
        if (currentRequestId !== columnRequestIdRef.current) {
          return;
        }
        if (!colonyRef.current.length || objName === 'Process') {
          onRefresh();
        } else {
          setColony([]);
          colonyRef.current = [];
        }
      }
    } finally {
      if (
        currentRequestId === columnRequestIdRef.current &&
        colonyRef.current.length
      ) {
        setTableLoading(false);
      }
    }
  };

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const handleTableChange = (
    pagination: any,
    filters?: Record<string, (React.Key | boolean)[] | null>
  ) => {
    let filterChanged = false;
    if (filters) {
      if ('base_instance_name' in filters) {
        const raw = filters.base_instance_name;
        const next = Array.isArray(raw)
          ? raw.map((item) => String(item))
          : [];
        if (!sameStringArray(next, colony)) {
          setColony(next);
          colonyRef.current = next;
          setNode(null);
          nodeRef.current = null;
          filterChanged = true;
        }
      }
      const nextColumnFilters = { ...columnFilters };
      let columnFilterChanged = false;
      tableColumn.forEach((col) => {
        const filterParam = col.filterParam as string | undefined;
        if (!filterParam || !(String(col.key) in filters)) {
          return;
        }
        const raw = filters[String(col.key)];
        const next = Array.isArray(raw)
          ? raw.map((item) => String(item))
          : [];
        const prev = nextColumnFilters[filterParam] || [];
        if (!sameStringArray(next, prev)) {
          if (next.length) {
            nextColumnFilters[filterParam] = next;
          } else {
            delete nextColumnFilters[filterParam];
          }
          columnFilterChanged = true;
        }
      });
      if (columnFilterChanged) {
        setColumnFilters(nextColumnFilters);
        columnFiltersRef.current = nextColumnFilters;
        filterChanged = true;
      }
    }
    if (filterChanged) {
      setTableData([]);
      setPagination((prev: Pagination) => ({
        ...prev,
        current: 1
      }));
      return;
    }
    setPagination(pagination);
  };

  const getAssetInsts = async (objectId: React.Key, type?: string) => {
    // 检查 objectId 是否还是当前活跃的，取消现有请求，再获取新的
    if (objectId !== currentObjectIdRef.current) {
      return;
    }
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    const currentRequestId = ++requestIdRef.current;
    const params = getParams();
    if (type === 'clear') {
      params.name = '';
    }
    try {
      setTableLoading(type !== 'timer');
      const request = showMultipleConditions
        ? getInstanceSearch
        : getInstanceList;
      const data = await request(objectId, params, {
        signal: abortController.signal
      });
      const results = data.results || [];
      const applied =
        currentRequestId === requestIdRef.current &&
        objectId === currentObjectIdRef.current;
      // 检查是否是最新的请求且 objectId 仍然匹配
      if (applied) {
        setTableData(results);
        setPagination((prev: Pagination) => ({
          ...prev,
          total: data.count || 0
        }));
      }
    } finally {
      // 只有当前请求且 objectId 匹配才更新 loading 状态
      if (
        currentRequestId === requestIdRef.current &&
        objectId === currentObjectIdRef.current
      ) {
        setTableLoading(false);
      }
    }
  };

  const linkToDetial = (app: TableDataItem) => {
    const monitorItem = objects.find(
      (item: ObjectItem) => sameMonitorId(item.id, objectId)
    );
    const encodedIdValues = encodeInstanceIdValuesParam(
      app.instance_id_values
    );
    const row: Record<string, string> = {
      monitorObjId: String(objectId || ''),
      name: monitorItem?.name || '',
      monitorObjDisplayName: monitorItem?.display_name || '',
      icon: monitorItem?.icon || OBJECT_DEFAULT_ICON,
      instance_id: String(app.instance_id || ''),
      instance_name: String(app.instance_name || ''),
      instance_id_values: encodedIdValues,
      instance_id_keys: Array.isArray(monitorItem?.instance_id_keys)
        ? monitorItem.instance_id_keys.join(',')
        : 'instance_id'
    };
    const params = withDashboardReturnContext(new URLSearchParams(row), {
      objectId: String(objectId || ''),
      objectName: String(monitorItem?.display_name || monitorItem?.name || '')
    });
    const professionalDashboardUrl = getProfessionalDashboardUrl(
      monitorItem?.name,
      monitorItem?.display_name,
      params.toString()
    );
    const targetUrl =
      professionalDashboardUrl || `/monitor/view/detail?${params.toString()}`;
    router.push(targetUrl);
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const onRefresh = () => {
    getAssetInsts(objectId);
  };

  const handleSelectFields = async (
    fieldKeys: string[],
    fixedFieldKeys: string[] = []
  ) => {
    const targetObjectId = objectId;
    await saveViewColumnPreference(
      targetObjectId,
      fieldKeys,
      fixedFieldKeys
    );
    if (currentObjectIdRef.current === targetObjectId) {
      setColumnPreference(fieldKeys);
      setFixedColumnPreference(fixedFieldKeys);
      message.success(t('common.saveSuccess'));
    }
  };

  const clearText = () => {
    setSearchText('');
    searchTextRef.current = '';
    getAssetInsts(objectId, 'clear');
  };

  const formatPlugins = (items: IntegrationItem[]): ViewPluginOption[] =>
    items
      .sort((a: IntegrationItem, b: IntegrationItem) => {
        const order = (item: IntegrationItem) =>
          item.is_pre ? 0 : !item.is_custom ? 1 : 2;
        return order(a) - order(b);
      })
      .map((item: IntegrationItem) => ({
        label: String(item.display_name || item.name || '--'),
        value: String(item.id)
      }));

  const openViewModal = async (row: TableDataItem) => {
    const effectivePlugins = await getEffectivePlugins(objectId, {
      instance_id: row.instance_id
    });
    setPlugins(formatPlugins(effectivePlugins || []));
    viewRef.current?.showModal({
      title: t('monitor.views.indexView'),
      type: 'add',
      form: row
    });
  };

  const handleColonyChange = (id: string) => {
    const next = id ? [id] : [];
    colonyRef.current = next;
    setColony(next);
    setNode(null);
    nodeRef.current = null;
    setTableData([]);
    setPagination((prev: Pagination) => ({
      ...prev,
      current: 1
    }));
  };

  const handleNodeChange = (id: string) => {
    setNode(id);
    nodeRef.current = id;
    setTableData([]);
    setPagination((prev: Pagination) => ({
      ...prev,
      current: 1
    }));
  };

  return (
    <div className="w-full">
      <div className="flex justify-between mb-[10px]">
        <div className="flex items-center">
          {showTopFilterBar && (
            <div className="flex items-center flex-wrap gap-y-[8px]">
              <span className="text-[14px] mr-[10px]">
                {t('monitor.views.filterOptions')}
              </span>
              {showTab && isPod && (
                <Select
                  value={node}
                  allowClear
                  showSearch
                  style={{ width: 240 }}
                  placeholder={t('monitor.views.node')}
                  onChange={handleNodeChange}
                >
                  {nodeList.map((item: ListItem, index: number) => (
                    <Option key={index} value={item.id}>
                      {item.name}
                    </Option>
                  ))}
                </Select>
              )}
              {!showTab && (
                <Select
                  value={colony[0] || null}
                  allowClear
                  showSearch
                  style={{ width: 240 }}
                  placeholder={instNamePlaceholder}
                  onChange={handleColonyChange}
                >
                  {queryData.map((item) => (
                    <Option key={item.id} value={item.id}>
                      {item.name || item.id}
                    </Option>
                  ))}
                </Select>
              )}
            </div>
          )}
          <Input
            allowClear
            className={`w-[240px] ${showTopFilterBar ? 'ml-[8px]' : ''}`}
            placeholder={t('common.searchPlaceHolder')}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onPressEnter={onRefresh}
            onClear={clearText}
          ></Input>
        </div>
        <TimeSelector
          onlyRefresh
          onFrequenceChange={onFrequenceChange}
          onRefresh={updatePage}
        />
      </div>
      <CustomTable
        scroll={{
          y: `calc(100vh - ${showTab ? '330px' : '280px'})`,
          x: 'max-content'
        }}
        columns={displayColumns}
        dataSource={tableData}
        pagination={pagination}
        loading={tableLoading}
        rowKey="instance_id"
        fieldSetting={{
          showSetting: true,
          displayFieldKeys: resolvedColumns.fieldKeys,
          choosableFields: fieldGroups.choosableFields,
          groupFields: fieldGroups.groups,
          searchable: true,
          modalWidth: 900,
          enableFixedFields: true,
          fixedFieldKeys:
            fixedColumnPreference == null ? undefined : fixedColumnPreference,
          defaultFixedFieldKeys: DEFAULT_VIEW_FIXED_FIELD_KEYS
        }}
        onSelectFields={handleSelectFields}
        onChange={handleTableChange}
      ></CustomTable>
      <ViewModal
        ref={viewRef}
        plugins={plugins}
        monitorObject={objectId}
        metrics={metrics}
        objects={objects}
        monitorName={findByMonitorId(objects, objectId)?.name || ''}
      />
    </div>
  );
};
export default ViewList;
