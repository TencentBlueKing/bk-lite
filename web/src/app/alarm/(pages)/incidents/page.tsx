'use client';

import React, { useState, useEffect } from 'react';
import LevelIcon from '@/app/alarm/components/levelIcon';
import AlarmFilters from '@/app/alarm/components/alarmFilters';
import CustomTable from '@/components/custom-table';
import alertStyle from './index.module.scss';
import TimeSelector from '@/components/time-selector';
import UserAvatar from '@/components/user-avatar';
import type { ColumnsType } from 'antd/es/table';
import { useIncidentsApi } from '@/app/alarm/api/incidents';
import { Input, Button, Tag } from 'antd';
import { Pagination, TimeSelectorDefaultValue } from '@/app/alarm/types/types';
import { IncidentTableDataItem } from '@/app/alarm/types/incidents';
import { FiltersConfig } from '@/app/alarm/types/alarms';
import { useTranslation } from '@/utils/i18n';
import { incidentStates } from '@/app/alarm/constants/alarm';
import { useRouter } from 'next/navigation';
import { useCommon } from '@/app/alarm/context/common';
import { KeepAlive, useActivate } from 'react-activation';

const IncidentsPage: React.FC = () => {
  const { getIncidentList } = useIncidentsApi();
  const { t } = useTranslation();
  const router = useRouter();
  const { levelListIncident, levelMapIncident } = useCommon();
  const [searchText, setSearchText] = useState('');
  const [data, setData] = useState<IncidentTableDataItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<FiltersConfig>({
    level: [],
    state: [],
    alarm_source: [],
  });
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const timeDefaultValue: TimeSelectorDefaultValue = {
    selectValue: 0,
    rangePickerVaule: null,
  };

  const stateOptions = incidentStates.map((val) => ({
    value: val,
    label: t(`alarms.${val}`),
  }));

  const handleRefresh = () => {
    fetchIncidentList();
  };

  const columns: ColumnsType<IncidentTableDataItem> = [
    {
      title: t('alarms.level'),
      dataIndex: 'level',
      key: 'level',
      width: 100,
      render: (_: any, { level }: IncidentTableDataItem) => {
        const target = levelListIncident.find(
          (item) => item.level_id === Number(level)
        );
        return (
          <Tag color={levelMapIncident[level || '']}>
            <div className="flex items-center">
              <LevelIcon icon={target?.icon || ''} className="mr-1 w-4 h-4" />
              {target?.level_display_name || '--'}
            </div>
          </Tag>
        );
      },
    },
    {
      title: t('alarms.createTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
    },
    {
      title: t('alarms.incidentName'),
      dataIndex: 'title',
      key: 'title',
      width: 180,
    },
    {
      title: t('alarms.source'),
      dataIndex: 'sources',
      key: 'sources',
      width: 140,
    },
    {
      title: t('incidents.alarmCount'),
      dataIndex: 'alert_count',
      key: 'alert_count',
      width: 140,
    },
    {
      title: t('alarms.state'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (val: string) => t(`alarms.${val}`),
    },
    {
      title: t('alarms.duration'),
      dataIndex: 'duration',
      key: 'duration',
      width: 120,
    },
    {
      title: t('alarms.assignee'),
      dataIndex: 'operator_users',
      key: 'operator_users',
      width: 200,
      shouldCellUpdate: (
        prev: IncidentTableDataItem,
        next: IncidentTableDataItem
      ) => prev?.operator_users !== next?.operator_users,
      render: (_: any, { operator_users }: IncidentTableDataItem) =>
        operator_users ? <UserAvatar userName={operator_users} /> : '--',
    },
    {
      title: t('alarmCommon.action'),
      key: 'action',
      fixed: 'right',
      width: 100,
      render: (_: any, record: IncidentTableDataItem) => (
        <div className="flex items-center">
          <Button
            type="link"
            onClick={() => {
              router.push(
                `/alarm/incidents/detail?id=${record.id}&incident_id=${record.incident_id}`
              );
            }}
          >
            {t('common.detail')}
          </Button>
        </div>
      ),
    },
  ];

  const fetchIncidentList = async (
    page?: number,
    pageSize?: number,
    titleSearch?: string
  ) => {
    try {
      setLoading(true);
      const res: any = await getIncidentList({
        title: titleSearch !== undefined ? titleSearch : searchText,
        page: page ?? pagination.current,
        page_size: pageSize ?? pagination.pageSize,
        level: filters.level.join(','),
        status: filters.state.join(','),
      });
      setData(res.items);
      setPagination((p) => ({
        ...p,
        total: res.count,
        current: page ?? p.current,
        pageSize: pageSize ?? p.pageSize,
      }));
      setLoading(false);
    } catch (error) {
      console.error('Error fetching incident list:', error);
      setLoading(false);
    }
  };

  useEffect(() => {
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchIncidentList(1, pagination.pageSize);
  }, [filters]);

  useActivate(() => {
    if (loading) return;
    fetchIncidentList();
  });

  const onFilterChange = (vals: string[], field: keyof FiltersConfig) => {
    setFilters((prev) => ({ ...prev, [field]: vals }));
  };
  const clearFilters = (field: keyof FiltersConfig) => {
    setFilters((prev) => ({ ...prev, [field]: [] }));
  };
  const onTableChange = (pag: any) =>
    fetchIncidentList(pag.current, pag.pageSize);

  const handleSearch = () => {
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchIncidentList(1, pagination.pageSize);
  };

  const handleSearchClear = () => {
    setSearchText('');
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchIncidentList(1, pagination.pageSize, '');
  };

  return (
    <div className={alertStyle.container}>
      <div className={alertStyle.filters}>
        <AlarmFilters
          filterSource={false}
          stateOptions={stateOptions}
          filters={filters}
          onFilterChange={onFilterChange}
          clearFilters={clearFilters}
        />
      </div>
      <div className={alertStyle.content}>
        <div className="flex items-center justify-between space-x-2 mb-[16px]">
          <Input
            allowClear
            className="w-[300px]"
            placeholder={t('common.search')}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onPressEnter={handleSearch}
            onClear={handleSearchClear}
          />
          <TimeSelector
            defaultValue={timeDefaultValue}
            onlyRefresh
            onRefresh={handleRefresh}
          />
        </div>
        <CustomTable
          rowKey="id"
          scroll={{ y: 'calc(100vh - 280px)', x: 'calc(100vw - 320px)' }}
          columns={columns}
          dataSource={data}
          pagination={pagination}
          loading={loading}
          onChange={onTableChange}
        />
      </div>
    </div>
  );
};

const Incidents = () => {
  return (
    <KeepAlive id="/alarm/incidents" name="/alarm/incidents">
      <IncidentsPage />
    </KeepAlive>
  );
};

export default Incidents;
