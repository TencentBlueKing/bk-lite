'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Tabs, Button, Spin, Descriptions, Empty, Card, Input } from 'antd';
import { CREATE_TASK_DETAIL_CONFIG } from '@/app/cmdb/constants/professCollection';
import { useCollectApi, useModelApi } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
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
        scroll={{ y: 'calc(100vh - 470px)' }}
        rowKey={(record) => record.id || record.inst_name || record.name}
      />
    </div>
  );
};

const TaskDetail: React.FC<TaskDetailProps> = ({ task, modelId, onClose }) => {
  const collectApi = useCollectApi();
  const modelApi = useModelApi();
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
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
    const hasData = rawData.length > 0;

    return (
      <div
        className="overflow-y-auto"
        style={{ height: 'calc(100vh - 310px)' }}
      >
        <div className="pr-2">
          {hasData ? (
            rawData.map((item: any, index: number) => (
              <div key={index} className="mb-6">
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
            ))
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('Collection.taskDetail.noRawData')}
            />
          )}
        </div>
      </div>
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
    loading,
    task.id,
    processColumns,
    statusColumn,
    errorColumn,
  ]);

  const statisticCards: StatisticCardConfig[] = useMemo(() => {
    const message = task.message || {};

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
        value: message.add_success || 0,
        bgColor: 'bg-blue-50',
        borderColor: 'border-blue-200',
        valueColor: 'text-blue-600',
        failedCount: message.add_error || 0,
        showFailed: (message.add_error || 0) > 0,
      },
      {
        title: t('Collection.taskDetail.updateData'),
        value: message.update_success || 0,
        bgColor: 'bg-orange-50',
        borderColor: 'border-orange-300',
        valueColor: 'text-orange-600',
        failedCount: message.update_error || 0,
        showFailed: (message.update_error || 0) > 0,
      },
      {
        title: t('Collection.taskDetail.deleteData'),
        value: message.delete_success || 0,
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

      <Tabs defaultActiveKey="add" items={tabItems} className="flex-1" />

      <div className="flex justify-start space-x-4 mt-4 px-4 pb-4">
        <Button onClick={onClose}>{t('common.close')}</Button>
      </div>
    </div>
  );
};

export default TaskDetail;
