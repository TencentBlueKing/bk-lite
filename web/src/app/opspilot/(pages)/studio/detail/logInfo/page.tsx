'use client';
import React, { useEffect, useState, useCallback } from 'react';
import { Input, Spin, Drawer, Button, Tag, Tooltip, Timeline, Segmented } from 'antd';
import { ClockCircleOutlined, SyncOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import type { ColumnType } from 'antd/es/table';
import useApiClient from '@/utils/request';
import ProChatComponent from '@/app/opspilot/components/studio/proChat';
import TimeSelector from '@/components/time-selector';
import CustomTable from '@/components/custom-table';
import { LogRecord, Channel, WorkflowTaskResult } from '@/app/opspilot/types/studio';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { fetchLogDetails, createConversation } from '@/app/opspilot/utils/logUtils';
import { useStudioApi } from '@/app/opspilot/api/studio';

const { Search } = Input;

const StudioLogsPage: React.FC = () => {
  const { t } = useTranslation();
  const { get, post } = useApiClient();
  const { fetchLogs, fetchChannels, fetchBotDetail, fetchWorkflowTaskResult, fetchWorkflowLogs } = useStudioApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [searchText, setSearchText] = useState('');
  const [dates, setDates] = useState<number[]>([]);
  const [data, setData] = useState<LogRecord[] | WorkflowTaskResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState<LogRecord | null>(null);
  const [conversationLoading, setConversationLoading] = useState(false);
  const [workflowDrawerVisible, setWorkflowDrawerVisible] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowTaskResult | null>(null);
  const [total, setTotal] = useState(0);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
  });
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [botType, setBotType] = useState<number | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string>('trigger');
  const [workflowLogsData, setWorkflowLogsData] = useState<LogRecord[]>([]);
  const [workflowLogsTotal, setWorkflowLogsTotal] = useState(0);
  const [workflowLogsPagination, setWorkflowLogsPagination] = useState({
    current: 1,
    pageSize: 10,
  });
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

  // Fetch workflow conversation logs for bot type 3
  const fetchWorkflowLogsData = useCallback(async (dates: number[] = [], page = 1, pageSize = 10) => {
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

      const res = await fetchWorkflowLogs(params);
      setWorkflowLogsData((res?.items || []).map((item: any, index: number) => ({
        key: index.toString(),
        title: item.title,
        createdTime: item.created_at,
        updatedTime: item.updated_at,
        user: item.user_id,
        channel: item.entry_type,
        count: item.count,
        ids: item.ids,
      })));
      setWorkflowLogsTotal(res.count || 0);
    } catch (error) {
      console.error(`${t('common.fetchFailed')}:`, error);
    }
    setLoading(false);
  }, [botId, fetchWorkflowLogs, t]);

  useEffect(() => {
    const initializeComponent = async () => {
      await fetchBotData();
      setInitialLoading(false);
    };
    
    initializeComponent();
  }, [fetchBotData]);

  useEffect(() => {
    if (botType !== null) {
      if (botType === 3) {
        if (activeTab === 'trigger') {
          fetchWorkflowData(dates, pagination.current, pagination.pageSize);
        } else {
          fetchWorkflowLogsData(dates, workflowLogsPagination.current, workflowLogsPagination.pageSize);
        }
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
  }, [botType, botId, dates, pagination.current, pagination.pageSize, activeTab, workflowLogsPagination.current, workflowLogsPagination.pageSize]);

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

  const handleWorkflowDetailClick = (record: WorkflowTaskResult) => {
    setSelectedWorkflow(record);
    setWorkflowDrawerVisible(true);
  };

  const renderJsonData = (data: any) => {
    if (!data) return '-';
    if (typeof data === 'object') {
      return <pre className="bg-gray-50 p-2 rounded text-xs overflow-auto max-h-60">{JSON.stringify(data, null, 2)}</pre>;
    }
    return String(data);
  };

  const renderWorkflowTimeline = () => {
    if (!selectedWorkflow?.output_data) return null;

    const nodes = Object.entries(selectedWorkflow.output_data).map(([key, value]: [string, any]) => ({
      id: key,
      name: value.name || key,
      type: value.type,
      index: value.index || 0,
      input_data: value.input_data,
      output: value.output,
    }));

    // 按 index 排序
    nodes.sort((a, b) => a.index - b.index);

    return (
      <Timeline
        items={nodes.map((node, idx) => ({
          color: idx === nodes.length - 1 ? 'green' : 'blue',
          children: (
            <div className="pb-4">
              <div className="font-medium text-base mb-2">
                {node.name}
                <Tag className="ml-2" color="blue">{node.type}</Tag>
              </div>
              <div className="space-y-3">
                <div>
                  <div className="text-gray-500 text-sm mb-1">{t('studio.logs.inputData')}:</div>
                  {renderJsonData(node.input_data)}
                </div>
                <div>
                  <div className="text-gray-500 text-sm mb-1">{t('studio.logs.outputData')}:</div>
                  {renderJsonData(node.output)}
                </div>
              </div>
            </div>
          ),
        }))}
      />
    );
  };

  const handleTableChange = (page: number, pageSize?: number) => {
    const newPagination = {
      current: page,
      pageSize: pageSize || pagination.pageSize,
    };
    setPagination(newPagination);
    
    if (botType === 3 && activeTab === 'trigger') {
      fetchWorkflowData(dates, newPagination.current, newPagination.pageSize);
    } else {
      fetchLogsData(searchText, dates, newPagination.current, newPagination.pageSize, selectedChannels);
    }
  };

  const handleWorkflowLogsTableChange = (page: number, pageSize?: number) => {
    const newPagination = {
      current: page,
      pageSize: pageSize || workflowLogsPagination.pageSize,
    };
    setWorkflowLogsPagination(newPagination);
    fetchWorkflowLogsData(dates, newPagination.current, newPagination.pageSize);
  };

  const handleRefresh = () => {
    if (botType === 3) {
      if (activeTab === 'trigger') {
        fetchWorkflowData(dates, pagination.current, pagination.pageSize);
      } else {
        fetchWorkflowLogsData(dates, workflowLogsPagination.current, workflowLogsPagination.pageSize);
      }
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
    setWorkflowLogsPagination({ ...workflowLogsPagination, current: 1 });
    
    if (botType === 3) {
      if (activeTab === 'trigger') {
        fetchWorkflowData(value, 1, pagination.pageSize);
      } else {
        fetchWorkflowLogsData(value, 1, workflowLogsPagination.pageSize);
      }
    } else {
      fetchLogsData(searchText, value, 1, pagination.pageSize, []);
    }
  };

  const handleTabChange = (key: string) => {
    setActiveTab(key);
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
      title: t('studio.logs.table.runTime'),
      dataIndex: 'run_time',
      key: 'run_time',
      render: (text) => convertToLocalizedTime(text),
    },
    {
      title: t('studio.logs.table.executeType'),
      dataIndex: 'execute_type',
      key: 'execute_type',
      render: (text) => {
        if (!text) return '-';
        return (
          <Tag color={text === 'restful' ? 'blue' : 'green'}>
            {text === 'restful' ? 'RESTful' : text.toUpperCase()}
          </Tag>
        );
      },
    },
    {
      title: t('studio.logs.table.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status, record) => {
        const statusText = status === 'success' 
          ? t('studio.logs.table.statusSuccess') 
          : status === 'failed' 
            ? t('studio.logs.table.statusFailed') 
            : t('studio.logs.table.statusRunning');
        
        const statusColor = status === 'success' ? 'green' : status === 'failed' ? 'red' : 'orange';
        
        if (status === 'failed' && record.error_log) {
          return (
            <Tooltip title={<pre className="max-w-md whitespace-pre-wrap">{record.error_log}</pre>}>
              <Tag color={statusColor}>{statusText}</Tag>
            </Tooltip>
          );
        }
        
        return <Tag color={statusColor}>{statusText}</Tag>;
      },
    },
    {
      title: t('studio.logs.table.executionDuration'),
      dataIndex: 'execution_duration',
      key: 'execution_duration',
      render: (duration) => `${duration || 0}ms`,
    },
    {
      title: t('studio.logs.table.actions'),
      key: 'actions',
      render: (text: any, record: WorkflowTaskResult) => (
        <Button type="link" onClick={() => handleWorkflowDetailClick(record)}>
          {t('studio.logs.table.detail')}
        </Button>
      ),
    },
  ];

  return (
    <div className='h-full flex flex-col'>
      <div className='mb-[20px]'>
        <div className='flex justify-between items-center'>
          {botType === 3 && (
            <Segmented
              value={activeTab}
              onChange={handleTabChange}
              options={[
                { label: t('studio.logs.triggerLogs'), value: 'trigger' },
                { label: t('studio.logs.conversationLogs'), value: 'conversation' },
              ]}
            />
          )}
          {botType !== 3 && <div />}
          <div className='flex space-x-4'>
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
      </div>
      <div className='flex-grow'>
        {initialLoading || loading ? (
          <div className='w-full flex items-center justify-center min-h-72'>
            <Spin size="large" />
          </div>
        ) : (
          <>
            {botType === 3 ? (
              <>
                {activeTab === 'trigger' ? (
                  <CustomTable<WorkflowTaskResult>
                    size="middle"
                    dataSource={data as WorkflowTaskResult[]}
                    columns={workflowColumns}
                    pagination={{
                      current: pagination.current,
                      pageSize: pagination.pageSize,
                      total: total,
                      showSizeChanger: true,
                      showQuickJumper: true,
                      onChange: handleTableChange,
                    }}
                  />
                ) : (
                  <CustomTable<LogRecord>
                    size="middle"
                    dataSource={workflowLogsData}
                    columns={logColumns}
                    pagination={{
                      current: workflowLogsPagination.current,
                      pageSize: workflowLogsPagination.pageSize,
                      total: workflowLogsTotal,
                      showSizeChanger: true,
                      showQuickJumper: true,
                      onChange: handleWorkflowLogsTableChange,
                    }}
                  />
                )}
              </>
            ) : (
              <CustomTable<LogRecord>
                size="middle"
                dataSource={data as LogRecord[]}
                columns={logColumns}
                pagination={{
                  current: pagination.current,
                  pageSize: pagination.pageSize,
                  total: total,
                  showSizeChanger: true,
                  showQuickJumper: true,
                  onChange: handleTableChange,
                }}
                scroll={{ y: 'calc(100vh - 370px)' }}
                onChange={(pagination, filters) => {
                  handleChannelFilterChange(filters.channel as string[]);
                }}
              />
            )}
          </>
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
      <Drawer
        title={t('studio.logs.workflowDetail')}
        open={workflowDrawerVisible}
        onClose={() => setWorkflowDrawerVisible(false)}
        width={720}
      >
        <div>
          {renderWorkflowTimeline()}
        </div>
      </Drawer>
    </div>
  );
};

export default StudioLogsPage;
