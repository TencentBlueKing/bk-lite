'use client';

import React, { useState, useEffect } from 'react';
import { Tabs, Button, Spin, Descriptions, Empty } from 'antd';
import CustomTable from '@/components/custom-table';
import type { CollectTask } from '@/app/cmdb/types/autoDiscovery';
import { CREATE_TASK_DETAIL_CONFIG } from '@/app/cmdb/constants/professCollection';
import styles from '../index.module.scss';
import { useCollectApi, useModelApi } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';

interface TaskDetailProps {
  task: CollectTask;
  modelId?: string;
  onClose?: () => void;
  onSuccess?: () => void;
}

interface TaskData {
  data: any[];
  count: number;
}

interface TaskDetailData {
  add: TaskData;
  update: TaskData;
  delete: TaskData;
  relation: TaskData;
  raw_data?: TaskData;
}

interface TaskTableProps {
  type: string;
  taskId: number;
  columns: any[];
  onClose?: () => void;
  onSuccess?: () => void;
  data: any[];
}

const TaskTable: React.FC<TaskTableProps> = ({ columns, data }) => {
  const [displayData, setDisplayData] = useState<any[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });

  useEffect(() => {
    if (data?.length) {
      updateDisplayData(data, pagination.current, pagination.pageSize);
      setPagination((prev) => ({
        ...prev,
        total: data.length,
      }));
    }
  }, [data]);

  const updateDisplayData = (
    data: any[],
    current: number,
    pageSize: number
  ) => {
    const start = (current - 1) * pageSize;
    const end = start + pageSize;
    setDisplayData(data.slice(start, end));
  };

  const handleTableChange = (newPagination: any) => {
    setPagination({ ...newPagination, total: data?.length || 0 });
    updateDisplayData(
      data || [],
      newPagination.current,
      newPagination.pageSize
    );
  };

  return (
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
      scroll={{ y: 'calc(100vh - 316px)' }}
      rowKey={(record) => record.id || record.inst_name || record.name}
    />
  );
};

const TaskDetail: React.FC<TaskDetailProps> = ({
  task,
  modelId,
  onClose,
  onSuccess,
}) => {
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

  const statusColumn = {
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
        <span className="text-red-500">{t('Collection.syncStatus.error')}</span>
      );
    },
  };

  const errorColumn = {
    title: t('Collection.taskDetail.errorInfo'),
    dataIndex: '_error',
    width: 200,
    render: (error: string) => (
      <span className="text-red-500">{error || '--'}</span>
    ),
  };

  const processColumns = (columns: any[]) => {
    return columns.map((col) => ({
      ...col,
      render: (text: any) => {
        if (col.dataIndex === 'asst_id') {
          return <span>{associationMap[text] || '--'}</span>;
        }
        return <span>{text || '--'}</span>;
      },
    }));
  };

  const renderRawDataTab = () => {
    const rawData = detailData.raw_data?.data || [];
    const hasData = rawData.length > 0;

    return (
      <div
        className="overflow-y-auto"
        style={{ height: 'calc(100vh - 206px)' }}
      >
        <div className="p-4">
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

  const tabItems = Object.entries(CREATE_TASK_DETAIL_CONFIG(t))
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
                onClose={onClose}
                onSuccess={onSuccess}
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

  // 添加原始数据 tab
  tabItems.push({
    key: 'raw_data',
    label: `${t('Collection.taskDetail.rawData')} (${detailData.raw_data?.count || 0})`,
    children: (
      <div className="flex flex-col h-full">
        <Spin spinning={loading}>{renderRawDataTab()}</Spin>
      </div>
    ),
  });

  return (
    <div className={`flex flex-col h-full rounded-lg ${styles.taskDetail}`}>
      <Tabs defaultActiveKey="add" items={tabItems} className="flex-1" />
      <div className="flex justify-start space-x-4 mt-4 px-4 pb-4">
        <Button onClick={onClose}>{t('common.close')}</Button>
      </div>
    </div>
  );
};

export default TaskDetail;
