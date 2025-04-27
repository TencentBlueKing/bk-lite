'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Input, Button, Progress, Select } from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import {
  deepClone,
  getEnumValueUnit,
  getEnumColor,
  getK8SData,
} from '@/app/monitor/utils/common';
import { useRouter } from 'next/navigation';
import {
  IntergrationItem,
  ObectItem,
  MetricItem,
  ViewListProps,
} from '@/app/monitor/types/monitor';
import ViewModal from './viewModal';
import {
  ColumnItem,
  ModalRef,
  Pagination,
  TableDataItem,
} from '@/app/monitor/types';
import { COLLECT_TYPE_MAP } from '@/app/monitor/constants/monitor';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import { INDEX_CONFIG } from '@/app/monitor/constants/monitor';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import Permission from '@/components/permission';
import { ListItem } from '@/types';
const { Option } = Select;

const ViewList: React.FC<ViewListProps> = ({ objects, objectId, showTab }) => {
  const { get, isLoading } = useApiClient();
  const { t } = useTranslation();
  const router = useRouter();
  const { convertToLocalizedTime } = useLocalizedTime();
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
  const [plugins, setPlugins] = useState<IntergrationItem[]>([]);
  const columns: ColumnItem[] = [
    {
      title: t('common.name'),
      dataIndex: 'instance_name',
      width: 140,
      ellipsis: true,
      key: 'instance_name',
    },
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
      title: t('monitor.intergrations.reportingStatus'),
      dataIndex: 'status',
      key: 'status',
      width: 160,
      // filters: [],
      render: (_, record) => (
        <>
          {record?.status ? t(`monitor.intergrations.${record.status}`) : '--'}
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
          <Permission requiredPermissions={['Detail']}>
            <Button type="link" onClick={() => linkToDetial(record)}>
              {t('monitor.views.overview')}
            </Button>
          </Permission>
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
    const params = getParams();
    const objParams = {
      monitor_object_id: objectId,
    };
    const objName = objects.find((item) => item.id === objectId)?.name;

    const getInstList = get(`/monitor/api/monitor_instance/${objectId}/list/`, {
      params,
    });
    const getQueryParams = get(
      `/monitor/api/monitor_instance/query_params_enum/${objName}/`,
      {
        params: objParams,
      }
    );
    const getMetrics = get('/monitor/api/metrics/', {
      params: objParams,
    });
    const getPlugins = get('/monitor/api/monitor_plugin/', {
      params: objParams,
    });
    setTableLoading(true);
    try {
      const res = await Promise.all([
        getInstList,
        getMetrics,
        getPlugins,
        getQueryParams,
      ]);
      const k8sQuery = res[3];
      const queryForm = isPod
        ? getK8SData(k8sQuery || {})
        : (k8sQuery || []).map((item: string) => ({ id: item, child: [] }));
      setQueryData(queryForm);
      const _plugins = res[2].map((item: IntergrationItem) => ({
        label: COLLECT_TYPE_MAP[item.name || ''],
        value: item.id,
      }));
      setPlugins(_plugins);
      setTableData(res[0]?.results || []);
      setPagination((prev: Pagination) => ({
        ...prev,
        total: res[0]?.count || 0,
      }));
      setMetrics(res[1] || []);
      const _objectName = objects.find((item) => item.id === objectId)?.name;
      if (_objectName) {
        const filterMetrics =
          INDEX_CONFIG.find((item) => item.name === _objectName)
            ?.tableDiaplay || [];
        const _columns = filterMetrics.map((item: any) => {
          const target = (res[1] || []).find(
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
            ...(item.type === 'value' ? {
              sorter: (a: any, b: any) => a[item.key] - b[item.key],
            } : {}),
            render: (_: unknown, record: TableDataItem) => {
              const color = getEnumColor(target, record[item.key]);
              return (
                <>
                  <span style={{ color }}>
                    {getEnumValueUnit(target, record[item.key])}
                  </span>
                </>
              );
            },
          };
        });
        const originColumns = deepClone(columns);
        const indexToInsert = originColumns.length - 1;
        originColumns.splice(indexToInsert, 0, ..._columns);
        setTableColumn(originColumns);
      }
    } catch (error) {
      console.log(error);
    } finally {
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
      const data = await get(
        `/monitor/api/monitor_instance/${objectId}/list/`,
        {
          params,
        }
      );
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
    const monitorItem = objects.find((item: ObectItem) => item.id === objectId);
    const row: any = {
      monitorObjId: objectId || '',
      name: monitorItem?.name || '',
      monitorObjDisplayName: monitorItem?.display_name || '',
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
          {showTab && (
            <div>
              <span className="text-[14px] mr-[10px]">
                {t('monitor.views.filterOptions')}
              </span>
              <Select
                value={colony}
                allowClear
                style={{ width: 120 }}
                placeholder={t('monitor.views.colony')}
                onChange={handleColonyChange}
              >
                {queryData.map((item) => (
                  <Option key={item.id} value={item.id}>
                    {item.id}
                  </Option>
                ))}
              </Select>
              {isPod && (
                <>
                  <Select
                    value={namespace}
                    allowClear
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
          onRefresh={onRefresh}
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
