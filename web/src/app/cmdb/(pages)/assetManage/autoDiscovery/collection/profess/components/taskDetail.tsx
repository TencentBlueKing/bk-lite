'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Tabs,
  Spin,
  Descriptions,
  Empty,
  Card,
  Input,
  Tag,
  Tooltip,
  Pagination,
  Button,
} from 'antd';
import { DownOutlined, UpOutlined } from '@ant-design/icons';
import {
  buildTopologyFactRowKey,
  CREATE_TASK_DETAIL_CONFIG,
  getTaskTopologyDisplayConfig,
  TOPOLOGY_FALLBACK_STRATEGY_OPTIONS,
  TOPOLOGY_PROTOCOL_OPTIONS,
} from '@/app/cmdb/constants/professCollection';
import { useCollectApi, useModelApi } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import TopologyGraphModal from './topologyGraphModal';
import styles from '../index.module.scss';
import type {
  CollectTask,
  TaskDetailData,
  TaskTableProps,
  StatisticCardConfig,
} from '@/app/cmdb/types/autoDiscovery';

interface TaskDetailProps {
  task: CollectTask;
  modelId?: string;
  onClose?: () => void;
  onSuccess?: () => void;
}

interface TopologyFactRow {
  __name__?: string;
  key?: string;
  instance_id?: string;
  source_protocol?: string;
  confidence?: string | number;
  local_device_id?: string;
  local_port_id?: string | number;
  local_port_name?: string;
  remote_device_id?: string;
  remote_port_id?: string | number;
  remote_port_name?: string;
  [key: string]: any;
}

// 拓扑链路快照里 inst_name 形如 `${device}-${端口名}`，展示时剥掉设备前缀只留端口名
const stripDevicePrefix = (
  instName?: string,
  device?: string
): string | undefined => {
  if (!instName) return instName;
  if (device && instName.startsWith(`${device}-`)) {
    return instName.slice(device.length + 1);
  }
  return instName;
};

const StatisticCard: React.FC<StatisticCardConfig> = ({
  title,
  value,
  bgColor,
  borderColor,
  valueColor,
  failedCount,
  showFailed = false,
}) => {
  const { t } = useTranslation();
  return (
    <Card size="small" className={`${bgColor} ${borderColor}`}>
      <div className="text-gray-600 text-xs mb-0.5">{title}</div>
      <div className={`text-2xl font-bold ${valueColor} mb-1`}>{value}</div>
      {showFailed && failedCount !== undefined && (
        <div className="text-xs font-medium text-red-600">
          {t('Collection.taskDetail.writeFailed')} {failedCount}{' '}
          {t('Collection.taskDetail.failedCount')}
        </div>
      )}
    </Card>
  );
};

const TaskTable: React.FC<TaskTableProps> = ({ columns, data }) => {
  const { t } = useTranslation();
  const [searchText, setSearchText] = useState('');
  const [pendingSearchText, setPendingSearchText] = useState('');
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });

  const filteredData = useMemo(() => {
    return searchText
      ? data.filter((item) =>
        String(item.inst_name || '')
          .toLowerCase()
          .includes(searchText.toLowerCase())
      )
      : data;
  }, [data, searchText]);

  const displayData = useMemo(() => {
    const startIndex = (pagination.current - 1) * pagination.pageSize;
    const endIndex = startIndex + pagination.pageSize;
    return filteredData.slice(startIndex, endIndex);
  }, [filteredData, pagination.current, pagination.pageSize]);

  useEffect(() => {
    setPagination((prev) => ({
      ...prev,
      current: 1,
      total: filteredData.length,
    }));
  }, [filteredData.length]);

  const handleTableChange = useCallback((newPagination: any) => {
    setPagination((prev) => ({
      ...prev,
      ...newPagination,
    }));
  }, []);

  const handleSearch = (value: string) => {
    setSearchText(value);
    setPendingSearchText(value);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="mb-4">
        <Input.Search
          placeholder={
            t('common.inputMsg') + t('Collection.taskDetail.instanceName')
          }
          className="w-60"
          allowClear
          value={pendingSearchText}
          onChange={(e) => setPendingSearchText(e.target.value)}
          onSearch={handleSearch}
        />
      </div>
      <CustomTable
        size="middle"
        columns={columns}
        dataSource={displayData}
        pagination={{
          ...pagination,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
        }}
        onChange={handleTableChange}
        scroll={{ y: 'calc(100vh - 440px)' }}
        rowKey={(record) => record.id || record.inst_name || record.name}
      />
    </div>
  );
};

// 拓扑摘要概览单元：label + 值，值区不换行，超出省略，鼠标移上去 tooltip 显示全文
const OverviewCell: React.FC<{
  label: string;
  tooltip?: React.ReactNode;
  labelWidth?: number;
  fullWidth?: boolean;
  children: React.ReactNode;
}> = ({ label, tooltip, labelWidth = 92, fullWidth, children }) => (
  <div
    className={`flex items-stretch border-b border-r border-[var(--color-border-1)] ${
      fullWidth ? 'md:col-span-2' : ''
    }`}
  >
    <div
      className="shrink-0 flex items-center px-3 py-2 text-xs text-[var(--color-text-3)] bg-[var(--color-fill-1)] border-r border-[var(--color-border-1)]"
      style={{ width: labelWidth }}
    >
      {label}
    </div>
    <div className="flex-1 min-w-0 px-3 py-2">
      <Tooltip title={tooltip}>
        <div className="truncate text-sm">{children}</div>
      </Tooltip>
    </div>
  </div>
);

// 拓扑摘要展开/收起状态持久化到浏览器，记住用户上一次的选择
const TOPOLOGY_COLLAPSED_STORAGE_KEY = 'cmdb:topologySummaryCollapsed';

const TaskDetail: React.FC<TaskDetailProps> = ({ task, modelId }) => {
  const collectApi = useCollectApi();
  const modelApi = useModelApi();
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [topologyCollapsed, setTopologyCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(TOPOLOGY_COLLAPSED_STORAGE_KEY) === '1';
  });

  const toggleTopologyCollapsed = useCallback(() => {
    setTopologyCollapsed((prev) => {
      const next = !prev;
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(
          TOPOLOGY_COLLAPSED_STORAGE_KEY,
          next ? '1' : '0'
        );
      }
      return next;
    });
  }, []);
  const [topologyGraphOpen, setTopologyGraphOpen] = useState(false);
  const [rawDataPage, setRawDataPage] = useState(1);
  const [rawDataPageSize, setRawDataPageSize] = useState(20);
  const [associationMap, setAssociationMap] = useState<Record<string, string>>(
    {}
  );
  const [detailData, setDetailData] = useState<TaskDetailData>({
    add: { data: [], count: 0 },
    update: { data: [], count: 0 },
    delete: { data: [], count: 0 },
    relation: { data: [], count: 0 },
    raw_data: { data: [], count: 0 },
  });

  useEffect(() => {
    const fetchDetailData = async () => {
      try {
        setLoading(true);
        const response = await collectApi.getCollectInfo(task.id.toString());
        setDetailData(response as TaskDetailData);
      } catch (error) {
        console.error('Failed to fetch task detail data:', error);
      } finally {
        setLoading(false);
      }
    };
    fetchDetailData();
  }, [task.id]);

  useEffect(() => {
    const fetchAssociationTypes = async () => {
      try {
        const response = await modelApi.getModelAssociationTypes();
        const associationMap = response.reduce(
          (acc: Record<string, string>, item: any) => {
            acc[item.asst_id] = item.asst_name;
            return acc;
          },
          {}
        );
        setAssociationMap(associationMap);
      } catch (error) {
        console.error('Failed to fetch association types:', error);
      }
    };

    fetchAssociationTypes();
  }, []);

  const isTopologyCapableTask =
    task.task_type === 'snmp' || task.model_id === 'network';

  const topologyDisplayConfig = useMemo(
    () =>
      isTopologyCapableTask
        ? getTaskTopologyDisplayConfig(task.params)
        : undefined,
    [isTopologyCapableTask, task.params]
  );

  const hasTopologySummary = Boolean(topologyDisplayConfig?.hasNetworkTopo);

  const protocolLabelMap = useMemo(
    () =>
      TOPOLOGY_PROTOCOL_OPTIONS.reduce<Record<string, string>>((acc, item) => {
        acc[item.value] = t(item.labelKey);
        return acc;
      }, {}),
    [t]
  );

  const fallbackStrategyLabelMap = useMemo(
    () =>
      TOPOLOGY_FALLBACK_STRATEGY_OPTIONS.reduce<Record<string, string>>(
        (acc, item) => {
          acc[item.value] = t(item.labelKey);
          return acc;
        },
        {}
      ),
    [t]
  );

  // 拓扑事实来自后端新流水线快照（detailData.topology.links），把链路映射成表格行结构。
  // 旧的 network_topology_facts_info_gauge 指标已废弃，不再从 raw_data 取。
  const topologyFacts = useMemo<TopologyFactRow[]>(() => {
    const links = detailData.topology?.links || [];
    return links.map((link) => ({
      source_protocol: link.evidence_source,
      confidence: link.confidence,
      instance_id: link.source_device,
      local_device_id: link.source_device,
      local_port_name:
        stripDevicePrefix(link.source_inst_name, link.source_device) ||
        link.source_port_id,
      remote_device_id: link.target_device || link.remote_device_name,
      remote_port_name:
        link.remote_port_name ||
        stripDevicePrefix(link.target_inst_name, link.target_device) ||
        link.target_port_id,
    }));
  }, [detailData.topology?.links]);

  const topologyProtocolSummary = useMemo(() => {
    const configuredProtocols = topologyDisplayConfig?.topologyProtocols || [];
    const observedProtocols = topologyFacts
      .map((fact) => fact.source_protocol)
      .filter((protocol): protocol is string => Boolean(protocol));
    const protocols = Array.from(new Set([...configuredProtocols, ...observedProtocols]));

    return protocols.map((protocol) => ({
      protocol,
      label: protocolLabelMap[protocol] || String(protocol).toUpperCase(),
      count: topologyFacts.filter((fact) => fact.source_protocol === protocol).length,
    }));
  }, [protocolLabelMap, topologyDisplayConfig?.topologyProtocols, topologyFacts]);

  const topologyFactTableData = useMemo(() => {
    const parseConfidence = (value: string | number | undefined) => {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : -1;
    };

    return topologyFacts
      .map((fact, index) => ({
        ...fact,
        key: buildTopologyFactRowKey(fact, index),
      }))
      .sort((a, b) => parseConfidence(b.confidence) - parseConfidence(a.confidence));
  }, [topologyFacts]);

  const statusColumn = useMemo(
    () => ({
      title: t('Collection.taskDetail.status'),
      dataIndex: '_status',
      width: 90,
      render: (status: string) => {
        if (status === 'success') {
          return (
            <span className="text-green-500">
              {t('Collection.syncStatus.success')}
            </span>
          );
        }
        return (
          <span className="text-red-500">
            {t('Collection.syncStatus.error')}
          </span>
        );
      },
    }),
    [t]
  );

  const errorColumn = useMemo(
    () => ({
      title: t('Collection.taskDetail.errorInfo'),
      dataIndex: '_error',
      width: 200,
      render: (error: string) =>
        error ? <span className="text-red-500">{error}</span> : <span>--</span>,
    }),
    [t]
  );

  const processColumns = useCallback(
    (columns: any[]) => {
      return columns.map((col) => ({
        ...col,
        render: (text: any) => {
          if (col.dataIndex === 'asst_id') {
            return <span>{associationMap[text] || '--'}</span>;
          }
          return <span>{text || '--'}</span>;
        },
      }));
    },
    [associationMap]
  );

  const renderRawDataTab = () => {
    const rawData = detailData.raw_data?.data || [];
    const total = rawData.length;
    const hasData = total > 0;
    // 原始数据量可能上千条，一次性渲染会卡。改为前端分页，只渲染当前页。
    const startIndex = (rawDataPage - 1) * rawDataPageSize;
    const pageData = rawData.slice(startIndex, startIndex + rawDataPageSize);

    if (!hasData) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('Collection.taskDetail.noRawData')}
        />
      );
    }

    return (
      <div className="flex flex-col" style={{ height: 'calc(100vh - 280px)' }}>
        <div className="flex-1 overflow-y-auto pr-2">
          {pageData.map((item: any, index: number) => (
            <div key={startIndex + index} className="mb-6">
              <Descriptions
                bordered
                size="small"
                column={1}
                labelStyle={{ width: 120 }}
              >
                {Object.entries(item).map(([key, value]: [string, any]) => (
                  <Descriptions.Item key={key} label={key}>
                    {typeof value === 'object' && value !== null
                      ? JSON.stringify(value)
                      : String(value || '--')}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            </div>
          ))}
        </div>
        <div className="flex justify-end pt-3 pr-2 border-t border-[var(--color-border-1)]">
          <Pagination
            size="small"
            current={rawDataPage}
            pageSize={rawDataPageSize}
            total={total}
            showSizeChanger
            pageSizeOptions={['10', '20', '50', '100']}
            showTotal={(count) => `共 ${count} 条`}
            onChange={(page, size) => {
              setRawDataPage(size !== rawDataPageSize ? 1 : page);
              setRawDataPageSize(size);
            }}
          />
        </div>
      </div>
    );
  };

  const renderTopologySummary = () => {
    if (!hasTopologySummary) {
      return null;
    }

    const configuredProtocols = topologyDisplayConfig?.topologyProtocols || [];
    const fallbackStrategy = topologyDisplayConfig?.topologyFallbackStrategy;
    const minConfidence = topologyDisplayConfig?.minConfidence;

    const protocolsText = configuredProtocols.length
      ? configuredProtocols
        .map((protocol) => protocolLabelMap[protocol] || String(protocol).toUpperCase())
        .join(' / ')
      : t('Collection.taskDetail.noTopologyProtocols');
    const fallbackText = fallbackStrategy
      ? fallbackStrategyLabelMap[fallbackStrategy] || fallbackStrategy
      : '--';
    const contributionText = topologyProtocolSummary.length
      ? topologyProtocolSummary.map((item) => `${item.label}: ${item.count}`).join('   ')
      : '--';

    return (
      <Card
        size="small"
        className="mb-4 border-[var(--color-border-1)] bg-[var(--color-bg-1)]"
        title={
          <span className="inline-flex items-center gap-3">
            {t('Collection.taskDetail.topologySummary')}
            {topologyFacts.length > 0 && (
              <Button
                type="link"
                size="small"
                className="px-0"
                onClick={() => setTopologyGraphOpen(true)}
              >
                {t('Collection.taskDetail.viewTopologyGraph')}
              </Button>
            )}
          </span>
        }
        extra={
          <Button
            type="text"
            size="small"
            icon={topologyCollapsed ? <DownOutlined /> : <UpOutlined />}
            onClick={toggleTopologyCollapsed}
          >
            {topologyCollapsed ? t('common.expand') : t('common.collapse')}
          </Button>
        }
        styles={{ body: { display: topologyCollapsed ? 'none' : undefined } }}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 border-t border-l border-[var(--color-border-1)] rounded overflow-hidden">
          <OverviewCell
            label={t('Collection.taskDetail.topologyProtocols')}
            tooltip={protocolsText}
          >
            {configuredProtocols.length ? (
              <span className="inline-flex items-center gap-2 align-middle">
                {configuredProtocols.map((protocol) => (
                  <Tag key={protocol} className="m-0">
                    {protocolLabelMap[protocol] || String(protocol).toUpperCase()}
                  </Tag>
                ))}
              </span>
            ) : (
              t('Collection.taskDetail.noTopologyProtocols')
            )}
          </OverviewCell>
          <OverviewCell
            label={t('Collection.taskDetail.topologyFallbackStrategy')}
            tooltip={fallbackText}
          >
            {fallbackText}
          </OverviewCell>
          <OverviewCell
            label={t('Collection.taskDetail.minConfidence')}
            tooltip={minConfidence ?? '--'}
          >
            {minConfidence ?? '--'}
          </OverviewCell>
          <OverviewCell
            label={t('Collection.taskDetail.topologyFactCount')}
            tooltip={topologyFacts.length}
          >
            {topologyFacts.length}
          </OverviewCell>
          <OverviewCell
            label={t('Collection.taskDetail.protocolContribution')}
            tooltip={contributionText}
            fullWidth
          >
            {topologyProtocolSummary.length ? (
              <span className="inline-flex items-center gap-2 align-middle">
                {topologyProtocolSummary.map((item) => (
                  <Tag key={item.protocol} className="m-0">
                    {item.label}: {item.count}
                  </Tag>
                ))}
              </span>
            ) : (
              '--'
            )}
          </OverviewCell>
        </div>
        <div className="mt-4">
          {topologyFacts.length ? (
            <CustomTable
              size="small"
              rowKey="key"
              columns={[
                {
                  title: t('Collection.taskDetail.protocol'),
                  dataIndex: 'source_protocol',
                  width: 120,
                  render: (value: string) =>
                    protocolLabelMap[value] || value?.toUpperCase() || '--',
                },
                {
                  title: t('Collection.taskDetail.confidence'),
                  dataIndex: 'confidence',
                  width: 120,
                  render: (value: string | number) => value ?? '--',
                },
                {
                  title: t('Collection.taskDetail.localPort'),
                  dataIndex: 'local_port_name',
                  render: (_: string, record: TopologyFactRow) =>
                    record.local_port_name || record.local_port_id || '--',
                },
                {
                  title: t('Collection.taskDetail.remoteDevice'),
                  dataIndex: 'remote_device_id',
                  render: (value: string) => value || '--',
                },
                {
                  title: t('Collection.taskDetail.remotePort'),
                  dataIndex: 'remote_port_name',
                  render: (_: string, record: TopologyFactRow) =>
                    record.remote_port_name || record.remote_port_id || '--',
                },
              ]}
              dataSource={topologyFactTableData.slice(0, 5)}
              pagination={false}
              scroll={{ x: 720 }}
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('Collection.taskDetail.noTopologyFacts')}
            />
          )}
        </div>
      </Card>
    );
  };

  const renderTopologyFactsTab = () => {
    if (!topologyFactTableData.length) {
      return (
        <div className="py-10">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t('Collection.taskDetail.noTopologyFacts')}
          />
        </div>
      );
    }

    return (
      <CustomTable
        size="middle"
        rowKey={(record: TopologyFactRow) => record.key}
        columns={[
          {
            title: t('Collection.taskDetail.protocol'),
            dataIndex: 'source_protocol',
            width: 120,
            render: (value: string) =>
              protocolLabelMap[value] || value?.toUpperCase() || '--',
          },
          {
            title: t('Collection.taskDetail.confidence'),
            dataIndex: 'confidence',
            width: 120,
            render: (value: string | number) => value ?? '--',
          },
          {
            title: t('Collection.taskDetail.localDevice'),
            dataIndex: 'instance_id',
            render: (_: string, record: TopologyFactRow) =>
              record.local_device_id || record.instance_id || '--',
          },
          {
            title: t('Collection.taskDetail.localPort'),
            dataIndex: 'local_port_name',
            render: (_: string, record: TopologyFactRow) =>
              record.local_port_name || record.local_port_id || '--',
          },
          {
            title: t('Collection.taskDetail.remoteDevice'),
            dataIndex: 'remote_device_id',
            render: (value: string) => value || '--',
          },
          {
            title: t('Collection.taskDetail.remotePort'),
            dataIndex: 'remote_port_name',
            render: (_: string, record: TopologyFactRow) =>
              record.remote_port_name || record.remote_port_id || '--',
          },
        ]}
        dataSource={topologyFactTableData}
        pagination={{
          showSizeChanger: true,
          showTotal: (total) =>
            t('Collection.taskDetail.paginationTotal', undefined, { total }),
        }}
        scroll={{ y: 'calc(100vh - 440px)', x: 960 }}
      />
    );
  };

  const tabItems = useMemo(() => {
    const items = Object.entries(CREATE_TASK_DETAIL_CONFIG(t))
      .filter(([key]) => !(modelId === 'k8s' && key === 'relation'))
      .map(([key, config]) => {
        const typeData = detailData[key as keyof TaskDetailData];
        const count =
          typeData && typeof typeData === 'object' && 'count' in typeData
            ? typeData.count
            : 0;
        const data = key === 'offline' ? detailData.delete : typeData;

        return {
          key,
          label: `${config.label} (${count})`,
          children: (
            <div className="flex flex-col h-full">
              <Spin spinning={loading}>
                <TaskTable
                  type={key}
                  taskId={task.id}
                  columns={[
                    ...processColumns(config.columns),
                    statusColumn,
                    errorColumn,
                  ]}
                  data={
                    data && typeof data === 'object' && 'data' in data
                      ? data.data
                      : []
                  }
                />
              </Spin>
            </div>
          ),
        };
      });

    if (hasTopologySummary) {
      items.push({
        key: 'topology_facts',
        label: `${t('Collection.taskDetail.topologyFacts')} (${topologyFacts.length})`,
        children: (
            <div className="flex flex-col h-full">
              <Spin spinning={loading}>{renderTopologyFactsTab()}</Spin>
            </div>
        ),
      });
    }

    items.push({
      key: 'raw_data',
      label: `${t('Collection.taskDetail.rawData')} (${detailData.raw_data?.count || 0})`,
      children: (
        <div className="flex flex-col h-full">
          <Spin spinning={loading}>{renderRawDataTab()}</Spin>
        </div>
      ),
    });

    return items;
  }, [
    t,
    modelId,
    detailData,
    hasTopologySummary,
    loading,
    task.id,
    topologyFacts.length,
    processColumns,
    statusColumn,
    errorColumn,
  ]);

  const statisticCards: StatisticCardConfig[] = useMemo(() => {
    const message = (task.message || {}) as any;

    return [
      {
        title: t('Collection.taskDetail.totalDiscovered'),
        value: message.all || 0,
        bgColor: 'bg-slate-100',
        borderColor: 'border-slate-300',
        valueColor: 'text-slate-700',
      },
      {
        title: t('Collection.taskDetail.addData'),
        value: message.add || 0,
        bgColor: 'bg-blue-50',
        borderColor: 'border-blue-200',
        valueColor: 'text-blue-600',
        failedCount: message.add_error || 0,
        showFailed: (message.add_error || 0) > 0,
      },
      {
        title: t('Collection.taskDetail.updateData'),
        value: message.update || 0,
        bgColor: 'bg-orange-50',
        borderColor: 'border-orange-300',
        valueColor: 'text-orange-600',
        failedCount: message.update_error || 0,
        showFailed: (message.update_error || 0) > 0,
      },
      {
        title: t('Collection.taskDetail.deleteData'),
        value: message.delete || 0,
        bgColor: 'bg-red-50',
        borderColor: 'border-red-300',
        valueColor: 'text-red-600',
        failedCount: message.delete_error || 0,
        showFailed: (message.delete_error || 0) > 0,
      },
    ];
  }, [task.message]);

  return (
    <div className={`flex flex-col h-full rounded-lg ${styles.taskDetail}`}>
      <div className="grid grid-cols-4 gap-4 mb-4">
        {statisticCards.map((card, index) => (
          <StatisticCard key={index} {...card} />
        ))}
      </div>

      {renderTopologySummary()}

      <Tabs defaultActiveKey="add" items={tabItems} className="flex-1" />

      <TopologyGraphModal
        open={topologyGraphOpen}
        onClose={() => setTopologyGraphOpen(false)}
        links={detailData.topology?.links || []}
      />
    </div>
  );
};

export default TaskDetail;
