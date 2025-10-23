'use client';

import React, { useEffect, useState } from 'react';
import { Card, Tooltip, Spin, message } from 'antd';
import { useSearchParams } from 'next/navigation';
import { InfoCircleOutlined } from '@ant-design/icons';
import { Line, LineConfig } from '@ant-design/charts';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';
import TimeSelector from '@/components/time-selector';
import { useStudioApi } from '@/app/opspilot/api/studio';

type DataField = 'conversationsData' | 'activeUsersData';

const ChartComponent: React.FC = () => {
  const { fetchConversations, fetchActiveUsers } = useStudioApi();
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;

  const getLast7Days = (): [number, number] => {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 7);
    return [start.getTime(), end.getTime()];
  };
  const [dates, setDates] = useState<number[]>(getLast7Days());

  const [conversationsData, setConversationsData] = useState<any[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(true);

  const [activeUsersData, setActiveUsersData] = useState<any[]>([]);
  const [loadingActiveUsers, setLoadingActiveUsers] = useState(true);

  const fetchAllData = async () => {
    const dateParams: any = {};
    if (dates && dates[0] && dates[1]) {
      dateParams.start_time = new Date(dates[0]).toISOString();
      dateParams.end_time = new Date(dates[1]).toISOString();
    }
    const params = { bot_id: id, ...dateParams };

    setLoadingConversations(true);
    fetchConversations(params)
      .then(dataResponse => {
        const combinedData: any[] = [];
        const totalData: any[] = [];
        for (const [key, values] of Object.entries(dataResponse)) {
          (values as any[]).forEach(item => {
            if (key === 'total') {
              totalData.push({ ...item, category: key });
            } else {
              combinedData.push({ ...item, category: key });
            }
          });
        }
        setConversationsData([...totalData, ...combinedData]);
      })
      .catch(() => message.error('Failed to fetch conversations data'))
      .finally(() => setLoadingConversations(false));

    setLoadingActiveUsers(true);
    fetchActiveUsers(params)
      .then(dataResponse => {
        const combinedData: any[] = [];
        const totalData: any[] = [];
        for (const [key, values] of Object.entries(dataResponse)) {
          (values as any[]).forEach(item => {
            if (key === 'total') {
              totalData.push({ ...item, category: key });
            } else {
              combinedData.push({ ...item, category: key });
            }
          });
        }
        setActiveUsersData([...totalData, ...combinedData]);
      })
      .catch(() => message.error('Failed to fetch activeUsers data'))
      .finally(() => setLoadingActiveUsers(false));
  };

  useEffect(() => {
    if (id) {
      fetchAllData();
    }
  }, [dates, id]);

  const handleDateChange = (value: number[]) => {
    setDates(value);
  };

  const lineConfig = (dataField: DataField): LineConfig => {
    let chartData: any[] = [];
    if (dataField === 'conversationsData') chartData = conversationsData;
    if (dataField === 'activeUsersData') chartData = activeUsersData;
    const isTokenOverview = false;
    return {
      data: chartData,
      xField: 'time',
      yField: 'count',
      seriesField: !isTokenOverview ? 'category' : undefined,
      smooth: !isTokenOverview,
      height: 250,
      autoFit: true,
      colorField: !isTokenOverview ? 'category' : undefined,
      scale: { color: { range: ['#155AEF', '#30BF78', '#FAAD14', '#b842ff'] } },
      tooltip: {
        items: [{ channel: 'y' }],
      },
    };
  };

  const renderCard = (titleKey: string, tooltipKey: string, children: React.ReactNode, key: string) => (
    <Card
      size="small"
      title={
        <div className="flex justify-between items-center">
          <span>{t(titleKey)}</span>
          <Tooltip title={t(tooltipKey)}>
            <InfoCircleOutlined className={`${styles.tipIcon}`} />
          </Tooltip>
        </div>
      }
      key={key}
    >
      {children}
    </Card>
  );

  return (
    <div className={`h-full flex flex-col ${styles.statisticsContainer}`}>
      <div className="flex justify-end mb-4">
        <TimeSelector
          onlyTimeSelect
          defaultValue={{
            selectValue: 10080,
            rangePickerVaule: null
          }}
          onChange={handleDateChange}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        {renderCard(
          'studio.statistics.totalConversation',
          'studio.statistics.totalConversationDesc',
          loadingConversations ? (
            <div className="flex justify-center items-center h-[250px]">
              <Spin size="large" />
            </div>
          ) : (
            <Line {...lineConfig('conversationsData')} />
          ),
          'totalConversation'
        )}
        {renderCard(
          'studio.statistics.totalActiveUser',
          'studio.statistics.totalActiveUserDesc',
          loadingActiveUsers ? (
            <div className="flex justify-center items-center h-[250px]">
              <Spin size="large" />
            </div>
          ) : (
            <Line {...lineConfig('activeUsersData')} />
          ),
          'totalActiveUser'
        )}
      </div>
    </div>
  );
};

export default ChartComponent;
