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
import { LogRecord, Channel } from '@/app/opspilot/types/studio';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { fetchLogDetails, createConversation } from '@/app/opspilot/utils/logUtils';
import { useStudioApi } from '@/app/opspilot/api/studio';

const { Search } = Input;

const StudioLogsPage: React.FC = () => {
  const { t } = useTranslation();
  const { get, post } = useApiClient();
  const { fetchLogs, fetchChannels } = useStudioApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [searchText, setSearchText] = useState('');
  const [dates, setDates] = useState<number[]>([]);
  const [data, setData] = useState<LogRecord[]>([]);
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
  const searchParams = useSearchParams();
  const botId = searchParams ? searchParams.get('id') : null;

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

  useEffect(() => {
    fetchLogsData();

    const fetchChannelsData = async () => {
      try {
        const data = await fetchChannels(botId);
        setChannels(data.map((channel: any) => ({ id: channel.id, name: channel.name })));
      } catch (error) {
        console.error(`${t('common.fetchFailed')}:`, error);
      }
    };
    fetchChannelsData();
  }, [botId]);

  const handleSearch = (value: string) => {
    setSearchText(value);
    setSelectedChannels([]);
    setPagination({ ...pagination, current: 1 });
    fetchLogsData(value, dates, 1, pagination.pageSize, []);
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
    fetchLogsData(searchText, dates, newPagination.current, newPagination.pageSize, selectedChannels);
  };

  const handleRefresh = () => {
    fetchLogsData(searchText, dates, pagination.current, pagination.pageSize, selectedChannels);
  };

  const handleChannelFilterChange = (channels: string[]) => {
    setSelectedChannels(channels);
    setPagination({ ...pagination, current: 1 });
    fetchLogsData(searchText, dates, 1, pagination.pageSize, channels);
  };

  const handleDateChange = (value: number[]) => {
    setDates(value);
    setSelectedChannels([]);
    setPagination({ ...pagination, current: 1 });
    fetchLogsData(searchText, value, 1, pagination.pageSize, []);
  };

  const channelFilters = channels.map(channel => ({ text: channel.name, value: channel.name }));

  const columns: ColumnType<LogRecord>[] = [
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
      onFilter: (value) => !!value,  // not used anymore
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
          <Table
            size="middle"
            dataSource={data}
            columns={columns}
            pagination={false}
            scroll={{ y: 'calc(100vh - 370px)' }}
            onChange={(pagination, filters) => handleChannelFilterChange(filters.channel as string[])}
          />
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
