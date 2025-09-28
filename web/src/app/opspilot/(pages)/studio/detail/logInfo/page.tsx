'use client';
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Input, Spin, Drawer, Button, Pagination, Tag, Tooltip } from 'antd';
import { ClockCircleOutlined, SyncOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import type { ColumnType } from 'antd/es/table';
import useApiClient from '@/utils/request';
import ProChatComponent from '@/app/opspilot/components/studio/proChat';
import TimeSelector from '@/components/time-selector';
import { LogRecord, Channel, WorkflowTaskResult } from '@/app/opspilot/types/studio';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { fetchLogDetails, createConversation } from '@/app/opspilot/utils/logUtils';
import { useStudioApi } from '@/app/opspilot/api/studio';

const { Search } = Input;

const StudioLogsPage: React.FC = () => {
  const { t } = useTranslation();
  const { get, post } = useApiClient();
  const { fetchLogs, fetchChannels, fetchBotDetail, fetchWorkflowTaskResult } = useStudioApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [searchText, setSearchText] = useState('');
  const [dates, setDates] = useState<number[]>([]);
  const [data, setData] = useState<LogRecord[] | WorkflowTaskResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState<LogRecord | null>(null);
  const [conversationLoading, setConversationLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
  });
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [botType, setBotType] = useState<number | null>(null);
  const searchParams = useSearchParams();
  const botId = searchParams ? searchParams.get('id') : null;

  // Fetch bot details and set bot type
  const fetchBotData = useCallback(async () => {
    try {
      const botDetail = await fetchBotDetail(botId);
      setBotType(botDetail.bot_type);
    } catch (error) {
      console.error('Failed to fetch bot details:', error);
    }
  }, [botId]);

  // Fetch logs data for regular bots (bot_type !== 3)
  const fetchLogsData = useCallback(async (searchText = '', dates: number[] = [], page = 1, pageSize = 10, selectedChannels: string[] = []) => {
    setLoading(true);
    try {
      const params: any = { bot_id: botId, page, page_size: pageSize };
      if (searchText) params.search = searchText;
      if (dates && dates[0] && dates[1]) {
        params.start_time = new Date(dates[0]).toISOString();
        params.end_time = new Date(dates[1]).toISOString();
      }
      if (selectedChannels.length > 0) params.channel_type = selectedChannels.join(',');

      const res = await fetchLogs(params);
      setData(res.items.map((item: any, index: number) => ({
        key: index.toString(),
        title: item.title,
        createdTime: item.created_at,
        updatedTime: item.updated_at,
        user: item.username,
        channel: item.channel_type,
        count: Math.ceil(item.count / 2),
        ids: item.ids,
      })));
      setTotal(res.count);
    } catch (error) {
      console.error(`${t('common.fetchFailed')}:`, error);
    }
    setLoading(false);
  }, [botId]);

  // Fetch workflow task results for bot type 3
  const fetchWorkflowData = useCallback(async (dates: number[] = [], page = 1, pageSize = 10) => {
    setLoading(true);
    try {
      const params: any = { 
        bot_id: botId,
        page, 
        page_size: pageSize 
      };
      
      if (dates && dates[0] && dates[1]) {
        params.start_time = new Date(dates[0]).toISOString();
        params.end_time = new Date(dates[1]).toISOString();
      }

      const res = await fetchWorkflowTaskResult(params);
      setData((res?.items || []).map((item: any, index: number) => {
        return {
          key: index.toString(),
          id: item.id,
          run_time: item.run_time,
          status: item.status,
          input_data: item.input_data,
          output_data: item.output_data,
          last_output: item.last_output,
          execute_type: item.execute_type,
          bot_work_flow: item.bot_work_flow,
          execution_duration: item.execution_duration || 0,
          error_log: item.error_log || '',
        };
      }));
      setTotal(res.count);
    } catch (error) {
      console.error(`${t('common.fetchFailed')}:`, error);
    }
    setLoading(false);
  }, [botId, fetchWorkflowTaskResult, t]);

  useEffect(() => {
    const initializeComponent = async () => {
      await fetchBotData();
    };
    
    initializeComponent();
  }, [fetchBotData]);

  useEffect(() => {
    if (botType !== null) {
      if (botType === 3) {
        fetchWorkflowData(dates, pagination.current, pagination.pageSize);
      } else {
        fetchLogsData(searchText, dates, pagination.current, pagination.pageSize, selectedChannels);
        
        const fetchChannelsData = async () => {
          try {
            const data = await fetchChannels(botId);
            setChannels(data.map((channel: any) => ({ id: channel.id, name: channel.name })));
          } catch (error) {
            console.error(`${t('common.fetchFailed')}:`, error);
          }
        };
        fetchChannelsData();
      }
    }
  }, [botType, botId, dates, pagination.current, pagination.pageSize]);

  const handleSearch = (value: string) => {
    setSearchText(value);
    setSelectedChannels([]);
    setPagination({ ...pagination, current: 1 });
    if (botType !== 3) {
      fetchLogsData(value, dates, 1, pagination.pageSize, []);
    }
  };

  const handleDetailClick = async (record: LogRecord) => {
    setSelectedConversation(record);
    setDrawerVisible(true);
    setConversationLoading(true);

    try {
      const data = await fetchLogDetails(post, record?.ids || []);
      const conversation = await createConversation(data, get);
      setSelectedConversation({
        ...record,
        conversation,
      });
    } catch (error) {
      console.error(`${t('common.fetchFailed')}:`, error);
    } finally {
      setConversationLoading(false);
    }
  };

  const handleTableChange = (page: number, pageSize?: number) => {
    const newPagination = {
      current: page,
      pageSize: pageSize || pagination.pageSize,
    };
    setPagination(newPagination);
    
    if (botType === 3) {
      fetchWorkflowData(dates, newPagination.current, newPagination.pageSize);
    } else {
      fetchLogsData(searchText, dates, newPagination.current, newPagination.pageSize, selectedChannels);
    }
  };

  const handleRefresh = () => {
    if (botType === 3) {
      fetchWorkflowData(dates, pagination.current, pagination.pageSize);
    } else {
      fetchLogsData(searchText, dates, pagination.current, pagination.pageSize, selectedChannels);
    }
  };

  const handleChannelFilterChange = (channels: string[]) => {
    setSelectedChannels(channels);
    setPagination({ ...pagination, current: 1 });
    if (botType !== 3) {
      fetchLogsData(searchText, dates, 1, pagination.pageSize, channels);
    }
  };

  const handleDateChange = (value: number[]) => {
    setDates(value);
    setSelectedChannels([]);
    setPagination({ ...pagination, current: 1 });
    
    if (botType === 3) {
      fetchWorkflowData(value, 1, pagination.pageSize);
    } else {
      fetchLogsData(searchText, value, 1, pagination.pageSize, []);
    }
  };

  const channelFilters = channels.map(channel => ({ text: channel.name, value: channel.name }));

  // Columns for regular logs (bot_type !== 3)
  const logColumns: ColumnType<LogRecord>[] = [
    {
      title: t('studio.logs.table.title'),
      dataIndex: 'title',
      key: 'title',
      render: (text) => (
        <Tooltip title={text}>
          <div className="line-clamp-3">{text}</div>
        </Tooltip>
      ),
    },
    {
      title: t('studio.logs.table.createdTime'),
      dataIndex: 'createdTime',
      key: 'createdTime',
      render: (text) => convertToLocalizedTime(text),
    },
    {
      title: t('studio.logs.table.updatedTime'),
      dataIndex: 'updatedTime',
      key: 'updatedTime',
      render: (text) => convertToLocalizedTime(text),
    },
    {
      title: t('studio.logs.table.user'),
      dataIndex: 'user',
      key: 'user',
    },
    {
      title: t('studio.logs.table.channel'),
      dataIndex: 'channel',
      key: 'channel',
      filters: channelFilters,
      filteredValue: selectedChannels,
      onFilter: (value) => !!value,
      filterMultiple: true,
    },
    {
      title: t('studio.logs.table.count'),
      dataIndex: 'count',
      key: 'count',
    },
    {
      title: t('studio.logs.table.actions'),
      key: 'actions',
      render: (text: any, record: LogRecord) => (
        <Button type="link" onClick={() => handleDetailClick(record)}>
          {t('studio.logs.table.detail')}
        </Button>
      ),
    },
  ];

  // Columns for workflow task results (bot_type === 3)
  const workflowColumns: ColumnType<WorkflowTaskResult>[] = [
    {
      title: '时间',
      dataIndex: 'run_time',
      key: 'run_time',
      render: (text) => convertToLocalizedTime(text),
    },
    {
      title: '触发方式',
      dataIndex: 'execute_type',
      key: 'execute_type',
      render: (text) => (
        <Tag color={text === 'restful' ? 'blue' : 'green'}>
          {text === 'restful' ? 'RESTful' : text.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: '执行状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => (
        <Tag color={status === 'success' ? 'green' : status === 'failed' ? 'red' : 'orange'}>
          {status === 'success' ? '成功' : status === 'failed' ? '失败' : '进行中'}
        </Tag>
      ),
    },
    {
      title: '执行耗时',
      dataIndex: 'execution_duration',
      key: 'execution_duration',
      render: (duration) => `${duration || 0}ms`,
    },
    {
      title: '错误日志',
      dataIndex: 'error_log',
      key: 'error_log',
      render: (errorLog) => (
        errorLog ? (
          <Tooltip title={errorLog}>
            <Tag color="red">有错误</Tag>
          </Tooltip>
        ) : (
          <Tag color="green">无错误</Tag>
        )
      ),
    },
  ];

  return (
    <div className='h-full flex flex-col'>
      <div className='mb-[20px]'>
        <div className='flex justify-end space-x-4'>
          <Search
            placeholder={`${t('studio.logs.searchUser')}...`}
            allowClear
            onSearch={handleSearch}
            enterButton
            className='w-60'
          />
          <Tooltip className='mr-[8px]' title={t('common.refresh')}>
            <Button icon={<SyncOutlined />} onClick={handleRefresh} />
          </Tooltip>
          <TimeSelector
            onlyTimeSelect
            defaultValue={{
              selectValue: 1440,
              rangePickerVaule: null
            }}
            onChange={handleDateChange}
          />
        </div>
      </div>
      <div className='flex-grow'>
        {loading ? (
          <div className='w-full flex items-center justify-center min-h-72'>
            <Spin size="large" />
          </div>
        ) : (
          <>
            {botType === 3 ? (
              <Table<WorkflowTaskResult>
                size="middle"
                dataSource={data as WorkflowTaskResult[]}
                columns={workflowColumns}
                pagination={false}
                scroll={{ y: 'calc(100vh - 370px)' }}
              />
            ) : (
              <Table<LogRecord>
                size="middle"
                dataSource={data as LogRecord[]}
                columns={logColumns}
                pagination={false}
                scroll={{ y: 'calc(100vh - 370px)' }}
                onChange={(pagination, filters) => {
                  handleChannelFilterChange(filters.channel as string[]);
                }}
              />
            )}
          </>
        )}
      </div>
      <div className='fixed bottom-8 right-8'>
        {!loading && total > 0 && (
          <Pagination
            total={total}
            showSizeChanger
            current={pagination.current}
            pageSize={pagination.pageSize}
            onChange={handleTableChange}
          />
        )}
      </div>
      <Drawer
        title={selectedConversation && (
          <div className="flex items-center">
            <span>{selectedConversation.user}</span>
            <Tag color="blue" className='ml-4' icon={<ClockCircleOutlined />}>{selectedConversation.count} {t('studio.logs.records')}</Tag>
          </div>
        )}
        open={drawerVisible}
        onClose={() => setDrawerVisible(false)}
        width={680}
      >
        {conversationLoading ? (
          <div className='flex justify-center items-center w-full h-full'>
            <Spin />
          </div>
        ) : (
          selectedConversation && selectedConversation.conversation && (
            <ProChatComponent
              initialChats={selectedConversation.conversation}
              conversationId={selectedConversation.ids || []}
              count={selectedConversation.count}
            />
          )
        )}
      </Drawer>
    </div>
  );
};

export default StudioLogsPage;
