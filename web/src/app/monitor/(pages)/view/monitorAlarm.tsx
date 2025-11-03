'use client';
import React, { useEffect, useState, useRef } from 'react';
import { Input, Button, Tag, message, Segmented, Popconfirm } from 'antd';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import { useTranslation } from '@/utils/i18n';
import {
  ColumnItem,
  ModalRef,
  Pagination,
  TableDataItem,
  UserItem,
  TimeSelectorDefaultValue,
  TimeValuesProps,
} from '@/app/monitor/types';
import { getRecentTimeRange } from '@/app/monitor/utils/common';
import { ViewModalProps } from '@/app/monitor/types/view';
import TimeSelector from '@/components/time-selector';
import Permission from '@/components/permission';
import AlertDetail from '@/app/monitor/(pages)/event/alert/alertDetail';
import CustomTable from '@/components/custom-table';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import dayjs from 'dayjs';
import { useCommon } from '@/app/monitor/context/common';
import { useLevelList, useStateMap } from '@/app/monitor/hooks';
import { LEVEL_MAP } from '@/app/monitor/constants';
import { INIT_VIEW_MODAL_FORM } from '@/app/monitor/constants/view';

const Alert: React.FC<ViewModalProps> = ({
  monitorObject,
  metrics,
  objects,
  form = INIT_VIEW_MODAL_FORM,
}) => {
  const { isLoading } = useApiClient();
  const { getMonitorAlert, patchMonitorAlert } = useMonitorApi();
  const { t } = useTranslation();
  const STATE_MAP = useStateMap();
  const LEVEL_LIST = useLevelList();
  const { convertToLocalizedTime } = useLocalizedTime();
  const commonContext = useCommon();
  const detailRef = useRef<ModalRef>(null);
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const [searchText, setSearchText] = useState<string>('');
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({
    timeRange: [],
    originValue: 10080,
  });
  const timeDefaultValue =
    useRef<TimeSelectorDefaultValue>({
      selectValue: 10080,
      rangePickerVaule: null,
    })?.current || {};
  const [activeTab, setActiveTab] = useState<string>('activeAlarms');
  const [frequence, setFrequence] = useState<number>(0);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const columns: ColumnItem[] = [
    {
      title: t('monitor.events.level'),
      dataIndex: 'level',
      key: 'level',
      width: 100,
      render: (_, { level }) => (
        <Tag color={LEVEL_MAP[level] as string}>
          {LEVEL_LIST.find((item) => item.value === level)?.label || '--'}
        </Tag>
      ),
    },
    {
      title: t('common.time'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      sorter: (a: any, b: any) => a.id - b.id,
      render: (_, { updated_at }) => (
        <>{updated_at ? convertToLocalizedTime(updated_at) : '--'}</>
      ),
    },
    {
      title: t('monitor.events.alertName'),
      dataIndex: 'content',
      key: 'content',
      width: 120,
    },
    {
      title: t('monitor.events.state'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (_, { status }) => (
        <Tag color={status === 'new' ? 'blue' : 'var(--color-text-4)'}>
          {STATE_MAP[status]}
        </Tag>
      ),
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <>
          <Button
            className="mr-[10px]"
            type="link"
            onClick={() => openAlertDetail(record)}
          >
            {t('common.detail')}
          </Button>
          <Permission
            requiredPermissions={['Detail']}
            instPermissions={record.permission}
          >
            <Popconfirm
              title={t('monitor.events.closeTitle')}
              description={t('monitor.events.closeContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              okButtonProps={{ loading: confirmLoading }}
              onConfirm={() => handleCloseConfirm(record)}
            >
              <Button type="link" disabled={record.status !== 'new'}>
                {t('common.close')}
              </Button>
            </Popconfirm>
          </Permission>
        </>
      ),
    },
  ];

  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      getAssetInsts('timer');
    }, frequence);
    return () => {
      clearTimer();
    };
  }, [
    frequence,
    timeValues,
    activeTab,
    searchText,
    pagination.current,
    pagination.pageSize,
  ]);

  useEffect(() => {
    if (isLoading) return;
    getAssetInsts('refresh');
  }, [
    isLoading,
    timeValues,
    activeTab,
    pagination.current,
    pagination.pageSize,
  ]);

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const changeTab = (val: string) => {
    setActiveTab(val);
  };

  const handleCloseConfirm = async (row: TableDataItem) => {
    setConfirmLoading(true);
    try {
      await patchMonitorAlert(row.id as string, {
        status: 'closed',
      });
      message.success(t('monitor.events.successfullyClosed'));
      onRefresh();
    } finally {
      setConfirmLoading(false);
    }
  };

  const getParams = () => {
    const recentTimeRange = getRecentTimeRange(timeValues);
    return {
      monitor_instance_id: form.instance_id,
      content: searchText,
      page: pagination.current,
      page_size: pagination.pageSize,
      monitor_object_id: monitorObject,
      created_at_after: dayjs(recentTimeRange[0]).toISOString(),
      created_at_before: dayjs(recentTimeRange[1]).toISOString(),
    };
  };

  const handleTableChange = (pagination: any) => {
    setPagination(pagination);
  };

  const getAssetInsts = async (type: string, text?: string) => {
    const params: any = getParams();
    if (text) {
      params.content = '';
    }
    if (activeTab === 'activeAlarms') {
      params.created_at_before = '';
      params.created_at_after = '';
      params.status_in = 'new';
    } else {
      params.status_in = 'recovered,closed';
    }
    try {
      setTableLoading(type !== 'timer');
      const data = await getMonitorAlert(params);
      setTableData(data.results);
      setPagination((pre) => ({
        ...pre,
        total: data.count,
      }));
    } finally {
      setTableLoading(false);
    }
  };

  const onTimeChange = (val: number[], originValue: number | null) => {
    setTimeValues({
      timeRange: val,
      originValue,
    });
  };

  const onRefresh = () => {
    getAssetInsts('refresh');
  };

  const openAlertDetail = (row: TableDataItem) => {
    const metricInfo =
      (metrics || []).find(
        (item) => item.id === row.policy?.query_condition?.metric_id
      ) || {};
    detailRef.current?.showModal({
      title: t('monitor.events.alertDetail'),
      type: 'add',
      form: {
        ...row,
        metric: metricInfo,
      },
    });
  };

  const enterText = () => {
    getAssetInsts('refresh');
  };

  const clearText = () => {
    setSearchText('');
    getAssetInsts('refresh', 'clear');
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  return (
    <div className="w-full">
      <Segmented
        className="mb-[16px]"
        value={activeTab}
        options={[
          {
            label: t('monitor.events.activeAlarms'),
            value: 'activeAlarms',
          },
          {
            label: t('monitor.events.historicalAlarms'),
            value: 'historicalAlarms',
          },
        ]}
        onChange={changeTab}
      />
      <div className="flex justify-between mb-[10px]">
        <Input
          allowClear
          className="w-[350px]"
          placeholder={t('common.searchPlaceHolder')}
          onChange={(e) => setSearchText(e.target.value)}
          onPressEnter={enterText}
          onClear={clearText}
        />
        <TimeSelector
          defaultValue={timeDefaultValue}
          onlyRefresh={activeTab === 'activeAlarms'}
          onFrequenceChange={onFrequenceChange}
          onChange={onTimeChange}
          onRefresh={onRefresh}
        />
      </div>
      <CustomTable
        scroll={{ y: 'calc(100vh - 412px)', x: 890 }}
        columns={columns}
        dataSource={tableData}
        pagination={pagination}
        loading={tableLoading}
        rowKey="id"
        onChange={handleTableChange}
      />
      <AlertDetail
        ref={detailRef}
        metrics={metrics}
        objects={objects}
        userList={userList}
        onSuccess={() => getAssetInsts('refresh')}
      />
    </div>
  );
};

export default Alert;
