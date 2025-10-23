'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Input, Button, Progress, Select } from 'antd';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import { useTranslation } from '@/utils/i18n';
import {
  getEnumValueUnit,
  getEnumColor,
  getK8SData,
  getBaseInstanceColumn,
} from '@/app/monitor/utils/common';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import { useRouter } from 'next/navigation';
import ViewModal from './viewModal';
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
  const { getCollectType, getTableDiaplay } = useObjectConfigInfo();
  const viewRef = useRef<ModalRef>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
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
  const [namespace, setNameSpace] = useState<string | null>(null);
  const [workload, setWorkload] = useState<string | null>(null);
  const [node, setNode] = useState<string | null>(null);
  const [colony, setColony] = useState<string | null>(null);
  const [queryData, setQueryData] = useState<any[]>([]);

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

  const namespaceList = useMemo(() => {
    if (queryData.length && colony) {
      return queryData.find((item) => item.id === colony)?.child || [];
    }
    return [];
  }, [colony, queryData]);

  const workloadList = useMemo(() => {
    if (namespaceList.length && namespace) {
      return (
        (
          namespaceList.find((item: ListItem) => item.id === namespace)
            ?.child || []
        ).filter((item: ListItem) => item.id === 'workload')[0]?.child || []
      );
    }
    return [];
  }, [namespaceList, namespace]);

  const nodeList = useMemo(() => {
    if (namespaceList.length && namespace) {
      return (
        (
          namespaceList.find((item: ListItem) => item.id === namespace)
            ?.child || []
        ).filter((item: ListItem) => item.id === 'node')[0]?.child || []
      );
    }
    return [];
  }, [namespaceList, namespace]);

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
  }, [colony, namespace, workload, node]);

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
        namespace: namespace || '',
        node: node || '',
        created_by_kind: workload || '',
        created_by_name:
          workloadList.find(
            (item: TableDataItem) => item.created_by_kind === workload
          )?.created_by_name || '',
      },
    };
  };

  const getColoumnAndData = async () => {
    const objParams = {
      monitor_object_id: objectId,
    };
    const targetObject = objects.find((item) => item.id === objectId);
    const objName = targetObject?.name;
    const getMetrics = getMonitorMetrics(objParams);
    const getPlugins = getMonitorPlugin(objParams);
    setTableLoading(true);
    try {
      const res = await Promise.all([
        getMetrics,
        getPlugins,
        showMultipleConditions &&
          getInstanceQueryParams(objName as string, objParams),
      ]);
      const k8sQuery = res[2];
      const queryForm = isPod
        ? getK8SData(k8sQuery || {})
        : (k8sQuery || []).map((item: string) => ({ id: item, child: [] }));
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
                t(`monitor.views.${[item.key]}`) ||
                target?.display_name ||
                '--',
              dataIndex: item.key,
              key: item.key,
              width: 300,
              sorter: (a: any, b: any) => a[item.key] - b[item.key],
              render: (_: unknown, record: TableDataItem) => (
                <Progress
                  className="flex"
                  strokeLinecap="butt"
                  showInfo={!!record[item.key]}
                  format={(percent) => `${percent?.toFixed(2)}%`}
                  percent={getPercent(record[item.key] || 0)}
                  percentPosition={{ align: 'start', type: 'outer' }}
                  size={[260, 20]}
                />
              ),
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
                sorter: (a: any, b: any) => a[item.key] - b[item.key],
              }
              : {}),
            render: (_: unknown, record: TableDataItem) => {
              const color = getEnumColor(target, record[item.key]);
              return (
                <>
                  <span style={{ color }}>
                    <EllipsisWithTooltip
                      text={getEnumValueUnit(target, record[item.key])}
                      className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
                    ></EllipsisWithTooltip>
                  </span>
                </>
              );
            },
          };
        });
        const originColumns = cloneDeep([
          ...getBaseInstanceColumn({
            objects,
            row: targetObject,
            t,
          }),
          ...columns,
        ]);
        const indexToInsert = originColumns.length - 1;
        originColumns.splice(indexToInsert, 0, ..._columns);
        setTableColumn(originColumns);
        if (!colony) {
          onRefresh();
        } else {
          setColony(null);
        }
      }
    } catch {
      setTableLoading(false);
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
    const params = getParams();
    if (type === 'clear') {
      params.name = '';
    }
    try {
      setTableLoading(type !== 'timer');
      const request = showMultipleConditions
        ? getInstanceSearch
        : getInstanceList;
      const data = await request(objectId, params);
      setTableData(data.results || []);
      setPagination((prev: Pagination) => ({
        ...prev,
        total: data.count || 0,
      }));
    } finally {
      setTableLoading(false);
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

  const handleSelectFields = (fields: string[]) => {
    console.log(fields);
  };

  const handleColonyChange = (id: string) => {
    setColony(id);
    setNameSpace(null);
    setWorkload(null);
    setNode(null);
    setTableData([]);
    setPagination((prev: Pagination) => ({
      ...prev,
      current: 1,
    }));
  };

  const handleNameSpaceChange = (id: string) => {
    setNameSpace(id);
    setWorkload(null);
    setNode(null);
    setTableData([]);
    setPagination((prev: Pagination) => ({
      ...prev,
      current: 1,
    }));
  };

  const handleWorkloadChange = (id: string) => {
    setWorkload(id);
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
                style={{ width: isPod ? 120 : 240 }}
                placeholder={instNamePlaceholder}
                onChange={handleColonyChange}
              >
                {queryData.map((item) => (
                  <Option key={item.id} value={item.id}>
                    {item.id}
                  </Option>
                ))}
              </Select>
              {showTab && isPod && (
                <>
                  <Select
                    value={namespace}
                    allowClear
                    showSearch
                    className="mx-[10px]"
                    style={{ width: 120 }}
                    placeholder={t('monitor.views.namespace')}
                    onChange={handleNameSpaceChange}
                  >
                    {namespaceList.map((item: ListItem) => (
                      <Option key={item.id} value={item.id}>
                        {item.id}
                      </Option>
                    ))}
                  </Select>
                  <Select
                    value={workload}
                    allowClear
                    showSearch
                    className="mr-[10px]"
                    style={{ width: 120 }}
                    placeholder={t('monitor.views.workload')}
                    onChange={handleWorkloadChange}
                  >
                    {workloadList.map((item: TableDataItem, index: number) => (
                      <Option key={index} value={item.created_by_kind}>
                        {item.created_by_name}
                      </Option>
                    ))}
                  </Select>
                  <Select
                    value={node}
                    allowClear
                    showSearch
                    style={{ width: 120 }}
                    placeholder={t('monitor.views.node')}
                    onChange={handleNodeChange}
                  >
                    {nodeList.map((item: string, index: number) => (
                      <Option key={index} value={item}>
                        {item}
                      </Option>
                    ))}
                  </Select>
                </>
              )}
            </div>
          )}
          <Input
            allowClear
            className="w-[240px] ml-[10px]"
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
          y: `calc(100vh - ${showTab ? '320px' : '270px'})`,
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
            'elasticsearch_fs_total_available_in_bytes',
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
        onSelectFields={handleSelectFields}
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
