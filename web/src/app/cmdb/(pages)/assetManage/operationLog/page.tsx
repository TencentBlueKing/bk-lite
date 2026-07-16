'use client';

import React, { useState, useEffect, useRef } from 'react';
import styles from './index.module.scss';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import CustomTable from '@/components/custom-table';
import Introduction from '@/components/introduction';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { Input, Select, DatePicker, message, Button } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useCommon } from '@/app/cmdb/context/common';
import { UserItem } from '@/app/cmdb/types/assetManage';
import { useChangeRecordApi } from '@/app/cmdb/api';

interface ListItem {
  id: string;
  oid: string;
  model: string;
  brand: string;
  device_type: string;
  built_in: boolean;
}

interface Filters {
  operator: undefined | string;
  type: undefined | string;
  scenarios: string[];
  message: string;
  dateRange: [Dayjs | null, Dayjs | null] | null;
}

// 操作日志默认筛除模型管理变更，保持实例主线视图
const DEFAULT_SCENARIOS = [
  'device_lifecycle',
  'relation_change',
  'ordinary_attribute_change',
  'collect_automation_change',
];

const OperationLog: React.FC = () => {
  const { t } = useTranslation();
  const commonContext = useCommon();

  const { getChangeRecords, getChangeRecordScenarioEnum, exportChangeRecords } =
    useChangeRecordApi();

  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [exporting, setExporting] = useState<boolean>(false);
  const [dataList, setDataList] = useState<ListItem[]>([]);
  const [columns, setColumns] = useState<any[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [scenarioEnum, setScenarioEnum] = useState<Record<string, string>>({});
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [filters, setFilters] = useState<Filters>({
    operator: undefined,
    type: undefined,
    scenarios: DEFAULT_SCENARIOS,
    message: '',
    dateRange: null,
  });

  const operationTypes = [
    {
      label: t('OperationLog.operationOpts.create_entity'),
      value: 'create_entity',
    },
    {
      label: t('OperationLog.operationOpts.update_entity'),
      value: 'update_entity',
    },
    {
      label: t('OperationLog.operationOpts.delete_entity'),
      value: 'delete_entity',
    },
    { label: t('OperationLog.operationOpts.execute'), value: 'execute' },
    {
      label: t('OperationLog.operationOpts.create_edge'),
      value: 'create_edge',
    },
    {
      label: t('OperationLog.operationOpts.delete_edge'),
      value: 'delete_edge',
    },
  ];

  const scenarioOptions = Object.keys(scenarioEnum).map((key) => ({
    label: scenarioEnum[key],
    value: key,
  }));

  const operators = userList.map((user: UserItem) => {
    const labelText = `${user.display_name}(${user.username})`;
    return {
      value: user.username,
      label: (
        <EllipsisWithTooltip
          text={labelText}
          className="whitespace-nowrap overflow-hidden text-ellipsis break-all"
        />
      ),
    };
  });

  useEffect(() => {
    setColumns(buildColumns());
    initScenarioEnum();
    getTableList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setColumns(buildColumns());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioEnum]);

  const initScenarioEnum = async () => {
    try {
      const data = await getChangeRecordScenarioEnum();
      setScenarioEnum(data || {});
    } catch {
      // ignore
    }
  };

  const buildQueryParams = (allParams: any) => ({
    page: allParams.current,
    page_size: allParams.pageSize,
    operator: allParams.operator,
    type: allParams.type,
    scenarios: allParams.scenarios?.length ? allParams.scenarios.join(',') : undefined,
    message: allParams.message,
    created_at_after: allParams.dateRange?.[0]?.format('YYYY-MM-DD HH:mm:ss'),
    created_at_before: allParams.dateRange?.[1]?.format('YYYY-MM-DD HH:mm:ss'),
  });

  const getTableList = async (params: any = {}) => {
    try {
      setTableLoading(true);
      const allParams = {
        ...pagination,
        ...filters,
        ...params,
      };
      const data = await getChangeRecords(buildQueryParams(allParams));
      setDataList(data.items || []);
      setPagination((prev) => ({
        ...prev,
        total: data.count || 0,
      }));
    } catch {
      message.error(t('common.loadListFailed'));
      return { data: [], total: 0, success: false };
    } finally {
      setTableLoading(false);
    }
  };

  const handleFilterChange = (key: string, value: any) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPagination((prev) => ({ ...prev, current: 1 }));
    getTableList({
      ...filters,
      ...pagination,
      [key]: value,
      current: 1,
    });
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
  };

  const handleInputSearch = () => {
    handleFilterChange('message', inputValue);
  };

  const handleInputClear = () => {
    setInputValue('');
    handleFilterChange('message', '');
  };

  const handleTableChange = (newPagination: any) => {
    setPagination(newPagination);
    getTableList({
      ...newPagination,
    });
  };

  const handleExport = async () => {
    try {
      setExporting(true);
      const params = buildQueryParams({ ...pagination, ...filters });
      // 导出不分页
      delete (params as any).page;
      delete (params as any).page_size;
      const blob = await exportChangeRecords(params);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `change_record_${dayjs().format('YYYYMMDD_HHmmss')}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      message.success(t('OperationLog.exportSuccess'));
    } catch {
      message.error(t('OperationLog.exportFailed'));
    } finally {
      setExporting(false);
    }
  };

  const buildColumns = () => {
    return [
      {
        title: t('OperationLog.operator'),
        dataIndex: 'operator',
        key: 'operator',
        width: 160,
      },
      {
        title: t('OperationLog.operationObject'),
        dataIndex: 'model_object',
        key: 'model_object',
        width: 160,
      },
      {
        title: t('OperationLog.operationType'),
        dataIndex: 'type',
        key: 'type',
        width: 120,
        render: (type: string) => t(`OperationLog.operationOpts.${type}`),
      },
      {
        title: t('OperationLog.scenario'),
        dataIndex: 'scenario',
        key: 'scenario',
        width: 140,
        render: (scenario: string) =>
          scenarioEnum[scenario] ||
          (scenario ? t(`OperationLog.scenarioOpts.${scenario}`) : '--'),
      },
      {
        title: t('OperationLog.operationTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 240,
        render: (time: string) => dayjs(time).format('YYYY-MM-DD HH:mm:ss'),
      },
      {
        title: t('OperationLog.summary'),
        dataIndex: 'message',
        key: 'message',
        width: 300,
      },
    ];
  };

  return (
    <div className={styles.container}>
      <Introduction
        title={t('OperationLog.title')}
        message={t('OperationLog.description')}
      />
      <div className={styles.content}>
        <div className={`${styles.filterWrapper} mb-[20px]`}>
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">
                {t('OperationLog.operator')}:
              </label>
              <Select
                allowClear
                showSearch
                style={{ width: 180 }}
                placeholder={t('common.selectTip')}
                options={operators}
                value={filters.operator}
                onChange={(value) => handleFilterChange('operator', value)}
                filterOption={(input, opt: any) => {
                  if (typeof opt?.label?.props?.text === 'string') {
                    return opt?.label?.props?.text
                      ?.toLowerCase()
                      .includes(input.toLowerCase());
                  }
                  return true;
                }}
              />
            </div>
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">
                {t('OperationLog.operationType')}:
              </label>
              <Select
                style={{ width: 160 }}
                placeholder={t('common.selectTip')}
                options={operationTypes}
                value={filters.type}
                onChange={(value) => handleFilterChange('type', value)}
                allowClear
              />
            </div>
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">
                {t('OperationLog.scenario')}:
              </label>
              <Select
                mode="multiple"
                style={{ minWidth: 220, maxWidth: 360 }}
                placeholder={t('common.selectTip')}
                options={scenarioOptions}
                value={filters.scenarios}
                onChange={(value) => handleFilterChange('scenarios', value || [])}
                allowClear
                maxTagCount="responsive"
              />
            </div>
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">
                {t('OperationLog.summary')}:
              </label>
              <Input
                style={{ width: 220 }}
                placeholder={t('common.inputTip')}
                value={inputValue}
                onChange={handleInputChange}
                onPressEnter={handleInputSearch}
                onClear={handleInputClear}
                allowClear
              />
            </div>
            <div className="flex items-center">
              <label className="mr-2 whitespace-nowrap">
                {t('OperationLog.timeRange')}:
              </label>
              <DatePicker.RangePicker
                style={{ width: 380 }}
                showTime
                value={filters.dateRange}
                onChange={(dates) => handleFilterChange('dateRange', dates)}
              />
            </div>
            <div className="flex items-center ml-auto">
              <Button
                icon={<DownloadOutlined />}
                loading={exporting}
                onClick={handleExport}
              >
                {t('OperationLog.export')}
              </Button>
            </div>
          </div>
        </div>
        <CustomTable
          size="middle"
          rowKey="id"
          loading={tableLoading}
          columns={columns}
          dataSource={dataList}
          pagination={pagination}
          onChange={handleTableChange}
          scroll={{ y: 'calc(100vh - 470px)' }}
        />
      </div>
    </div>
  );
};

export default OperationLog;
