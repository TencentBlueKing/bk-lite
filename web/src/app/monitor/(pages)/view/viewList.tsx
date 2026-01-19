'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Input, Button, Progress, Select } from 'antd';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import { useTranslation } from '@/utils/i18n';
import {
  getEnumColor,
  getBaseInstanceColumn,
} from '@/app/monitor/utils/common';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import { useRouter } from 'next/navigation';
import ViewModal from './viewModal';
import MetricDimensionTooltip from './metricDimensionTooltip';
import {
  ColumnItem,
  ModalRef,
  Pagination,
  TableDataItem,
  IntegrationItem,
  ObjectItem,
  MetricItem,
} from '@/app/monitor/types';
import { ViewListProps } from '@/app/monitor/types/view';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { ListItem } from '@/types';
import {
  OBJECT_DEFAULT_ICON,
  DERIVATIVE_OBJECTS,
} from '@/app/monitor/constants';
import { cloneDeep } from 'lodash';
const { Option } = Select;

const ViewList: React.FC<ViewListProps> = ({
  objects,
  objectId,
  showTab,
  updateTree,
}) => {
  const { isLoading } = useApiClient();
  const { getMonitorMetrics, getInstanceList, getMonitorPlugin } =
    useMonitorApi();
  const { getInstanceSearch, getInstanceQueryParams } = useViewApi();
  const { t } = useTranslation();
  const router = useRouter();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getEnumValueUnit } = useUnitTransform();
  const { getCollectType, getTableDiaplay } = useObjectConfigInfo();
  const viewRef = useRef<ModalRef>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef<number>(0);
  const columnAbortControllerRef = useRef<AbortController | null>(null);
  const columnRequestIdRef = useRef<number>(0);
  const currentObjectIdRef = useRef<React.Key>(objectId);
  const [searchText, setSearchText] = useState<string>('');
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [frequence, setFrequence] = useState<number>(0);
  const [plugins, setPlugins] = useState<IntegrationItem[]>([]);
  const columns: ColumnItem[] = [
    {
      title: t('monitor.views.reportTime'),
      dataIndex: 'time',
      key: 'time',
      width: 160,
      sorter: (a: any, b: any) => a.time - b.time,
      render: (_, { time }) => (
        <>{time ? convertToLocalizedTime(new Date(time * 1000) + '') : '--'}</>
      ),
    },
    {
      title: t('monitor.integrations.reportingStatus'),
      dataIndex: 'status',
      key: 'status',
      width: 160,
      render: (_, record) => (
        <>
          {record?.status ? t(`monitor.integrations.${record.status}`) : '--'}
        </>
      ),
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
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
      ),
    },
  ];
  const [tableColumn, setTableColumn] = useState<ColumnItem[]>(columns);
  const [metrics, setMetrics] = useState<MetricItem[]>([]);
  const [node, setNode] = useState<string | null>(null);
  const [colony, setColony] = useState<string | null>(null);
  const [queryData, setQueryData] = useState<any[]>([]);
  const [nodeList, setNodeList] = useState<ListItem[]>([]);

  const instNamePlaceholder = useMemo(() => {
    const type = objects.find((item) => item.id === objectId)?.type || '';
    const baseTarget = objects
      .filter((item) => item.type === type)
      .find((item) => item.level === 'base');
    const title: string = baseTarget?.display_name || t('monitor.source');
    return title;
  }, [objects, objectId]);

  const isPod = useMemo(() => {
    return objects.find((item) => item.id === objectId)?.name === 'Pod';
  }, [objects, objectId]);

  const showMultipleConditions = useMemo(() => {
    const objectNames = DERIVATIVE_OBJECTS.filter(
      (item) => !['Pod', 'Node'].includes(item)
    );
    const currentObjectName = objects.find(
      (item) => item.id === objectId
    )?.name;
    return objectNames.includes(currentObjectName as string) || showTab;
  }, [objects, objectId]);

  useEffect(() => {
    if (isLoading) return;
    if (objectId && objects?.length) {
      currentObjectIdRef.current = objectId;
      cancelAllRequests();
      setTableData([]);
      setPagination((prev: Pagination) => ({
        ...prev,
        current: 1,
      }));
      getColoumnAndData();
    }
  }, [objectId, objects, isLoading]);

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
    searchText,
  ]);

  // 条件过滤请求
  useEffect(() => {
    if (objectId && objects?.length && !isLoading) {
      onRefresh();
    }
  }, [colony, node]);

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
    return {
      page: pagination.current,
      page_size: pagination.pageSize,
      add_metrics: true,
      name: searchText,
      vm_params: {
        instance_id: colony || '',
        node: node || '',
      },
    };
  };

  const getColoumnAndData = async () => {
    // 取消上一次未完成的列相关请求
    columnAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    columnAbortControllerRef.current = abortController;
    const currentRequestId = ++columnRequestIdRef.current;
    const objParams = {
      monitor_object_id: objectId,
    };
    const targetObject = objects.find((item) => item.id === objectId);
    const objName = targetObject?.name;
    const config = { signal: abortController.signal };
    const getMetrics = getMonitorMetrics(objParams, config);
    const getPlugins = getMonitorPlugin(objParams, config);
    setTableLoading(true);
    try {
      const res = await Promise.all([
        getMetrics,
        getPlugins,
        showMultipleConditions &&
          getInstanceQueryParams(objName as string, objParams, config),
      ]);
      // 检查是否是最新的请求
      if (currentRequestId !== columnRequestIdRef.current) {
        return;
      }
      const k8sQuery = res[2];
      let queryForm: any[] = [];
      if (k8sQuery?.cluster) {
        queryForm = k8sQuery?.cluster || [];
        setNodeList(k8sQuery?.node || []);
      } else {
        queryForm = (k8sQuery || []).map((item: any) => {
          if (typeof item === 'string') {
            return { id: item, child: [] };
          }
          return {
            id: item?.id,
            name: item?.name || '',
            child: [],
          };
        });
      }
      setQueryData(queryForm);
      const _plugins = res[1].map((item: IntegrationItem) => ({
        label: getCollectType(objName as string, item.name as string),
        value: item.id,
      }));
      setPlugins(_plugins);
      setMetrics(res[0] || []);
      if (objName) {
        const filterMetrics = getTableDiaplay(objName);
        const _columns = filterMetrics.map((item: any) => {
          const target = (res[0] || []).find(
            (tex: MetricItem) => tex.name === item.key
          );
          if (item.type === 'progress') {
            return {
              title:
                target?.display_name ||
                t(`monitor.views.${[item.key]}`) ||
                '--',
              dataIndex: item.key,
              key: item.key,
              width: 300,
              sorter: (a: any, b: any) => a[item.key] - b[item.key],
              render: (_: unknown, record: TableDataItem) => {
                const hasDimensions = record.has_dimensions || false;
                return (
                  <div className="flex items-center justify-between">
                    <Progress
                      className="flex"
                      strokeLinecap="butt"
                      showInfo={!!record[item.key]}
                      format={(percent) => `${percent?.toFixed(2)}%`}
                      percent={getPercent(record[item.key]?.value || 0)}
                      percentPosition={{ align: 'start', type: 'outer' }}
                      size={[220, 20]}
                    />
                    {hasDimensions && (
                      <MetricDimensionTooltip
                        instanceId={record.instance_id}
                        metricName={item.key}
                        monitorObjectId={objectId}
                      />
                    )}
                  </div>
                );
              },
            };
          }
          return {
            title:
              t(`monitor.views.${[item.key]}`) || target?.display_name || '--',
            dataIndex: item.key,
            key: item.key,
            width: 200,
            ...(item.type === 'value'
              ? {
                sorter: (a: any, b: any) => a[item.key]?.value - b[item.key]?.value,
              }
              : {}),
            render: (_: unknown, record: TableDataItem) => {
              const color = getEnumColor(target, record[item.key]?.value);
              const hasDimensions = record.has_dimensions || false;
              const metricValue = record[item.key]?.value;
              const metricUnit = record[item.key]?.unit || target?.unit || '';
              const metricItem: any = {
                unit: metricUnit,
                name: target?.name,
              };
              return (
                <div className="flex items-center justify-between">
                  <span style={{ color }}>
                    <EllipsisWithTooltip
                      text={getEnumValueUnit(
                        metricItem,
                        metricValue,
                        metricUnit
                      )}
                      className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
                    ></EllipsisWithTooltip>
                  </span>
                  {hasDimensions && (
                    <MetricDimensionTooltip
                      instanceId={record.instance_id}
                      metricName={item.key}
                      monitorObjectId={objectId}
                    />
                  )}
                </div>
              );
            },
          };
        });
        const originColumns = cloneDeep([
          ...getBaseInstanceColumn({
            objects,
            row: targetObject,
            t,
            queryData: queryForm,
          }),
          ...columns,
        ]);
        const indexToInsert = originColumns.length - 1;
        originColumns.splice(indexToInsert, 0, ..._columns);
        setTableColumn(originColumns);
        if (currentRequestId !== columnRequestIdRef.current) {
          return;
        }
        if (!colony) {
          onRefresh();
        } else {
          setColony(null);
        }
      }
    } finally {
      if (currentRequestId === columnRequestIdRef.current && colony) {
        setTableLoading(false);
      }
    }
  };

  const getPercent = (value: number) => {
    return +(+value).toFixed(2);
  };
  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const handleTableChange = (pagination: any) => {
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
        signal: abortController.signal,
      });
      // 检查是否是最新的请求且 objectId 仍然匹配
      if (
        currentRequestId === requestIdRef.current &&
        objectId === currentObjectIdRef.current
      ) {
        setTableData(data.results || []);
        setPagination((prev: Pagination) => ({
          ...prev,
          total: data.count || 0,
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
      (item: ObjectItem) => item.id === objectId
    );
    const row: any = {
      monitorObjId: objectId || '',
      name: monitorItem?.name || '',
      monitorObjDisplayName: monitorItem?.display_name || '',
      icon: monitorItem?.icon || OBJECT_DEFAULT_ICON,
      instance_id: app.instance_id,
      instance_name: app.instance_name,
      instance_id_values: app.instance_id_values,
    };
    const params = new URLSearchParams(row);
    const targetUrl = `/monitor/view/detail?${params.toString()}`;
    router.push(targetUrl);
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const onRefresh = () => {
    getAssetInsts(objectId);
  };

  const clearText = () => {
    setSearchText('');
    getAssetInsts(objectId, 'clear');
  };

  const openViewModal = (row: TableDataItem) => {
    viewRef.current?.showModal({
      title: t('monitor.views.indexView'),
      type: 'add',
      form: row,
    });
  };

  const handleColonyChange = (id: string) => {
    setColony(id);
    setNode(null);
    setTableData([]);
    setPagination((prev: Pagination) => ({
      ...prev,
      current: 1,
    }));
  };

  const handleNodeChange = (id: string) => {
    setNode(id);
    setTableData([]);
    setPagination((prev: Pagination) => ({
      ...prev,
      current: 1,
    }));
  };

  return (
    <div className="w-full">
      <div className="flex justify-between mb-[10px]">
        <div className="flex items-center">
          {showMultipleConditions && (
            <div>
              <span className="text-[14px] mr-[10px]">
                {t('monitor.views.filterOptions')}
              </span>
              <Select
                value={colony}
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
              {showTab && isPod && (
                <>
                  <Select
                    className="ml-[8px]"
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
                </>
              )}
            </div>
          )}
          <Input
            allowClear
            className="w-[240px] ml-[8px]"
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
          x: 'calc(100vw - 300px)',
        }}
        columns={tableColumn}
        dataSource={tableData}
        pagination={pagination}
        loading={tableLoading}
        rowKey="instance_id"
        fieldSetting={{
          showSetting: false,
          displayFieldKeys: [
            'elasticsearch_cluster_health_status_code',
            'instance_name',
          ],
          choosableFields: tableColumn.slice(0, tableColumn.length - 1),
          groupFields: [
            {
              title: t('monitor.events.basicInformation'),
              key: 'baseInfo',
              child: columns.slice(0, 2),
            },
            {
              title: t('monitor.events.metricInformation'),
              key: 'metricInfo',
              child: tableColumn.slice(2, tableColumn.length - 1),
            },
          ],
        }}
        onChange={handleTableChange}
      ></CustomTable>
      <ViewModal
        ref={viewRef}
        plugins={plugins}
        monitorObject={objectId}
        metrics={metrics}
        objects={objects}
        monitorName={objects.find((item) => item.id === objectId)?.name || ''}
      />
    </div>
  );
};
export default ViewList;
