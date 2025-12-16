'use client';

import React, { useState, useEffect, FC } from 'react';
import dayjs from 'dayjs';
import SearchFilter from '@/app/alarm/components/searchFilter';
import EventTable from '@/app/alarm/components/eventTable';
import CustomBreadcrumb from '@/app/alarm/components/customBreadcrumb';
import { CopyOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { SourceItem } from '@/app/alarm/types/integration';
import { useAlarmApi } from '@/app/alarm/api/alarms';
import { EventItem } from '@/app/alarm/types/alarms';
import { useSourceApi } from '@/app/alarm/api/integration';
import { Empty, Descriptions, message, Tabs, DatePicker, Spin } from 'antd';

const IntegrationDetail: FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { getAlertSourcesDetail } = useSourceApi();
  const { getEventList } = useAlarmApi();
  const [loading, setLoading] = useState<boolean>(false);
  const [source, setSource] = useState<SourceItem>();
  const [activeTab, setActiveTab] = useState<string>('event');
  const [eventList, setEventList] = useState<EventItem[]>([]);
  const [eventLoading, setEventLoading] = useState<boolean>(false);
  const [timeRange, setTimeRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>();
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [searchCondition, setSearchCondition] = useState<{
    field: string;
    value: string;
  } | null>(null);

  const sourceItemId = searchParams.get('sourceItemId');

  useEffect(() => {
    if (sourceItemId) {
      getSourceDetail();
    }
  }, [sourceItemId]);

  const getSourceDetail = async () => {
    setLoading(true);
    try {
      const res = await getAlertSourcesDetail(sourceItemId as string);
      if (res) {
        setSource(res);
      }
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const copySecret = (text: string = '') => {
    navigator.clipboard.writeText(text);
    message.success(t('alarmCommon.copied'));
  };

  const fetchEventList = async () => {
    setEventLoading(true);
    try {
      const params: any = {
        source_id: source?.source_id,
        page: pagination.current,
        page_size: pagination.pageSize,
        received_at_before: timeRange?.[1]?.toISOString(),
        received_at_after: timeRange?.[0]?.toISOString(),
      };
      if (searchCondition) {
        params[searchCondition.field] = searchCondition.value;
      }
      const res = await getEventList(params);
      setEventList(res.items || []);
      setPagination((prev) => ({ ...prev, total: res.count }));
    } finally {
      setEventLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'event' && source?.source_id) {
      fetchEventList();
    }
  }, [
    activeTab,
    source,
    pagination.current,
    pagination.pageSize,
    searchCondition,
    timeRange,
  ]);

  const onFilterSearch = (condition: { field: string; value: string }) => {
    setSearchCondition(condition);
    setPagination((prev) => ({ ...prev, current: 1 }));
  };

  const eventAttrList = [
    { attr_id: 'title', attr_name: '标题', attr_type: 'str', option: [] },
    { attr_id: 'description', attr_name: '内容', attr_type: 'str', option: [] },
  ];

  const IntegrationHeader = () => (
    <div className="flex items-center">
      <div className="inline-flex items-center gap-3 mr-4 px-6 py-4 rounded bg-[#99aaf2] text-white">
        <img
          src={source?.logo || ''}
          alt={source?.description}
          className="h-[40px] rounded"
        />
        <span className="text-[24px] font-semibold">{source?.name}</span>
      </div>
      <span className="text-[15px]">{source?.description}</span>
    </div>
  );

  const renderGuideTab = () => (
    <div className="p-4 max-h-[calc(100vh-330px)] overflow-y-auto">
      <h4 className="mb-2 font-medium pl-2 border-l-4 border-blue-400 inline-block leading-tight">
        {t('integration.baseInfo')}
      </h4>
      <Descriptions
        bordered
        size="small"
        column={1}
        labelStyle={{ width: 120 }}
      >
        <Descriptions.Item label="ID">{source?.source_id}</Descriptions.Item>
        <Descriptions.Item label="url">{source?.config.url}</Descriptions.Item>
        <Descriptions.Item label="method">
          {source?.config.method}
        </Descriptions.Item>
        <Descriptions.Item label="headers">
          {JSON.stringify(source?.config.headers)}
        </Descriptions.Item>
        <Descriptions.Item label="params">
          {JSON.stringify(source?.config.params)}
        </Descriptions.Item>
        <Descriptions.Item label="content_type">
          {source?.config.content_type}
        </Descriptions.Item>
        <Descriptions.Item label="description">
          {source?.description}
        </Descriptions.Item>
        <Descriptions.Item label="secret">
          {'******************'}
          <CopyOutlined
            className="ml-[10px]"
            onClick={() => copySecret(source?.secret)}
          />
        </Descriptions.Item>
        <Descriptions.Item label="CURL">
          <div className="relative">
            <pre className="bg-[var(--color-bg-5)] p-2 pr-10 rounded border border-[var(--color-border-1)] text-[13px] font-mono leading-relaxed whitespace-pre-wrap break-all max-w-full">
              <code>{source?.config?.examples?.CURL || ''}</code>
            </pre>
            <CopyOutlined
              className="absolute top-3 right-3 cursor-pointer hover:text-blue-500"
              onClick={() => copySecret(source?.config?.examples?.CURL)}
            />
          </div>
        </Descriptions.Item>
        <Descriptions.Item label="Python">
          <div className="relative">
            <pre className="bg-[var(--color-bg-5)] p-2 pr-10 rounded border border-[var(--color-border-1)] text-[13px] font-mono leading-relaxed whitespace-pre-wrap break-all max-w-full">
              <code>{source?.config?.examples?.Python || ''}</code>
            </pre>
            <CopyOutlined
              className="absolute top-3 right-3 cursor-pointer hover:text-blue-500"
              onClick={() => copySecret(source?.config?.examples?.Python)}
            />
          </div>
        </Descriptions.Item>
      </Descriptions>
      <h4 className="mt-6 mb-2 font-medium pl-2 border-l-4 border-blue-400 inline-block leading-tight">
        {t('integration.eventFieldsMapping')}
      </h4>
      <Descriptions
        bordered
        size="small"
        column={1}
        labelStyle={{ width: 120 }}
      >
        {Object.entries(source?.config?.event_fields_mapping as any).map(
          ([key, val]: any) => (
            <Descriptions.Item key={key} label={key}>
              {val}
            </Descriptions.Item>
          )
        )}
      </Descriptions>
      <h4 className="mt-6 mb-2 font-medium pl-2 border-l-4 border-blue-400 inline-block leading-tight">
        {t('integration.eventFieldsDescription')}
      </h4>
      <Descriptions
        bordered
        size="small"
        column={1}
        labelStyle={{ width: 120 }}
      >
        {Object.entries(source?.config?.event_fields_desc_mapping as any).map(
          ([key, desc]: any) => (
            <Descriptions.Item key={key} label={key}>
              {desc}
            </Descriptions.Item>
          )
        )}
      </Descriptions>
    </div>
  );

  if (!sourceItemId) {
    return <Empty description={t('common.noData')} />;
  }

  return (
    <div className="w-full flex-1">
      <CustomBreadcrumb />

      <Spin spinning={loading}>
        {!source ? (
          <div className="mt-[24vh]">
            {!loading && <Empty description={t('common.noData')} />}
          </div>
        ) : (
          <>
            <div className="p-4 bg-[var(--color-bg-1)] rounded">
              <IntegrationHeader />
            </div>
            <div className="p-4 bg-[var(--color-bg-1)] rounded pt-0 mt-4">
              <Tabs activeKey={activeTab} onChange={setActiveTab}>
                <Tabs.TabPane key="event" tab={t('integration.eventTab')}>
                  <div className="mb-4 flex items-center gap-6">
                    <SearchFilter
                      attrList={eventAttrList}
                      onSearch={onFilterSearch}
                    />
                    <div>
                      <span className="mr-2">{t('integration.timeRange')}</span>
                      <DatePicker.RangePicker
                        showTime={{ format: 'HH:mm:ss' }}
                        value={timeRange}
                        onChange={(vals) => {
                          setTimeRange(vals as [dayjs.Dayjs, dayjs.Dayjs]);
                          setPagination((prev) => ({ ...prev, current: 1 }));
                        }}
                      />
                    </div>
                  </div>
                  <EventTable
                    dataSource={eventList}
                    loading={eventLoading}
                    pagination={pagination}
                    tableScrollY="calc(100vh - 490px)"
                    onChange={(pag) =>
                      setPagination({
                        current: pag.current || 1,
                        pageSize: pag.pageSize || pagination.pageSize,
                        total: pagination.total,
                      })
                    }
                  />
                </Tabs.TabPane>
                <Tabs.TabPane key="guide" tab={t('integration.guideTab')}>
                  {renderGuideTab()}
                </Tabs.TabPane>
              </Tabs>
            </div>
          </>
        )}
      </Spin>
    </div>
  );
};

export default IntegrationDetail;
