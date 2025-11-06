'use client';

import React, { useState, useEffect, useRef } from 'react';
import { message, Select, Space, Button, Tag, Input, Checkbox, Progress } from 'antd';
import { SearchOutlined, DownloadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import { useSecurityApi } from '@/app/system-manager/api/security';
import OperateModal from '@/components/operate-modal';
import type { ColumnsType } from 'antd/es/table';
import type { TableRowSelection } from 'antd/es/table/interface';
import dayjs from 'dayjs';
import * as XLSX from 'xlsx';

const UserLoginLogs: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getUserLoginLogs } = useSecurityApi();
  const timeSelectorRef = useRef<any>(null);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<any[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [selectedRows, setSelectedRows] = useState<any[]>([]);
  const [exportModalVisible, setExportModalVisible] = useState(false);
  const [exportFormats, setExportFormats] = useState<string[]>(['excel']);
  const [exporting, setExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0
  });
  const [filters, setFilters] = useState<{
    status?: 'success' | 'failed';
    username?: string;
    source_ip?: string;
  }>({});
  const [timeRange, setTimeRange] = useState<number[]>(() => {
    const end = dayjs().valueOf();
    const start = dayjs().subtract(7, 'day').valueOf();
    return [start, end];
  });

  useEffect(() => {
    fetchLogs();
  }, []);

  const fetchLogs = async (page = 1, pageSize = 10) => {
    try {
      setLoading(true);
      const params: any = {
        page,
        page_size: pageSize
      };

      if (filters.status) {
        params.status = filters.status;
      }
      if (filters.username) {
        params.username__icontains = filters.username;
      }
      if (filters.source_ip) {
        params.source_ip__icontains = filters.source_ip;
      }
      if (timeRange && timeRange.length === 2) {
        params.login_time_start = dayjs(timeRange[0]).format('YYYY-MM-DD HH:mm:ss');
        params.login_time_end = dayjs(timeRange[1]).format('YYYY-MM-DD HH:mm:ss');
      }

      const response = await getUserLoginLogs(params);
      setLogs(response.items || []);
      setPagination({
        current: page,
        pageSize,
        total: response.count || 0
      });
    } catch (error) {
      console.error('Failed to fetch user logs:', error);
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    fetchLogs(1, pagination.pageSize);
  };

  const handleReset = () => {
    setFilters({});
    setTimeRange([]);
    if (timeSelectorRef.current?.reset) {
      timeSelectorRef.current.reset();
    }
    setTimeout(() => {
      fetchLogs(1, pagination.pageSize);
    }, 0);
  };

  const handleTimeChange = (range: number[]) => {
    setTimeRange(range);
  };

  const handleTableChange = (page: number, pageSize: number) => {
    fetchLogs(page, pageSize);
  };

  const rowSelection: TableRowSelection<any> = {
    selectedRowKeys,
    onChange: (keys: React.Key[], rows: any[]) => {
      setSelectedRowKeys(keys);
      setSelectedRows(rows);
    }
  };

  const handleExport = () => {
    if (selectedRowKeys.length === 0) {
      message.warning(t('system.security.pleaseSelectRows'));
      return;
    }
    setExportModalVisible(true);
  };

  const handleExportConfirm = async () => {
    if (exportFormats.length === 0) {
      message.warning(t('system.security.selectFormat'));
      return;
    }

    setExporting(true);
    setExportProgress(0);

    try {
      const exportData = selectedRows.map((row) => ({
        [t('system.user.table.username')]: row.username,
        [t('system.security.loginTime')]: convertToLocalizedTime(row.login_time),
        [t('system.security.loginLocation')]: row.location,
        [t('system.security.operatingSystem')]: row.os_info,
        [t('system.security.browser')]: row.browser_info,
        [t('system.security.loginHost')]: row.source_ip,
        [t('system.security.loginStatus')]: row.status_display
      }));

      setExportProgress(30);

      if (exportFormats.includes('excel')) {
        const ws = XLSX.utils.json_to_sheet(exportData);
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Login Logs');
        setExportProgress(60);
        XLSX.writeFile(wb, `login_logs_${dayjs().format('YYYYMMDD_HHmmss')}.xlsx`);
      }

      setExportProgress(80);

      if (exportFormats.includes('csv')) {
        const headers = Object.keys(exportData[0]);
        const csvContent = [
          headers.join(','),
          ...exportData.map((row) =>
            headers.map((header) => `"${row[header] || ''}"`).join(',')
          )
        ].join('\n');

        const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `login_logs_${dayjs().format('YYYYMMDD_HHmmss')}.csv`;
        link.click();
        URL.revokeObjectURL(link.href);
      }

      setExportProgress(100);
      message.success(t('system.security.exportSuccess'));
      setExportModalVisible(false);
    } catch (error) {
      console.error('Export failed:', error);
      message.error(t('system.security.exportFailed'));
    } finally {
      setTimeout(() => {
        setExporting(false);
        setExportProgress(0);
      }, 500);
    }
  };

  const handleExportCancel = () => {
    setExportModalVisible(false);
    setExportFormats(['excel']);
  };


  const columns: ColumnsType<any> = [
    {
      title: t('system.user.table.username'),
      dataIndex: 'username',
      key: 'username'
    },
    {
      title: t('system.security.loginTime'),
      dataIndex: 'login_time',
      key: 'login_time',
      render: (text: string) => convertToLocalizedTime(text)
    },
    {
      title: t('system.security.loginLocation'),
      dataIndex: 'location',
      key: 'location'
    },
    {
      title: t('system.security.operatingSystem'),
      dataIndex: 'os_info',
      key: 'os_info'
    },
    {
      title: t('system.security.browser'),
      dataIndex: 'browser_info',
      key: 'browser_info'
    },
    {
      title: t('system.security.loginHost'),
      dataIndex: 'source_ip',
      key: 'source_ip'
    },
    {
      title: t('system.security.loginStatus'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string, record: any) => {
        return (
          <Tag color={status === 'success' ? 'green' : 'red'}>
            {record.status_display}
          </Tag>
        );
      }
    }
  ];

  return (
    <div className="bg-[var(--color-bg)] p-4 rounded-lg">
      <Space direction="vertical" className="w-full" size="middle">
        <div className="flex justify-end">
          <Space wrap>
            <Select
              placeholder={t('system.security.loginStatus')}
              className="w-[120px]"
              allowClear
              value={filters.status}
              onChange={(value) => setFilters({ ...filters, status: value })}
              options={[
                { label: t('system.security.loginStatusSuccess'), value: 'success' },
                { label: t('system.security.loginStatusFailed'), value: 'failed' }
              ]}
            />
            <Input
              placeholder={t('system.user.table.username')}
              className="w-[200px]"
              allowClear
              value={filters.username}
              onChange={(e) => setFilters({ ...filters, username: e.target.value })}
            />
            <Input
              placeholder={t('system.security.sourceIpPlaceholder')}
              className="w-[200px]"
              allowClear
              value={filters.source_ip}
              onChange={(e) => setFilters({ ...filters, source_ip: e.target.value })}
            />
            <TimeSelector
              ref={timeSelectorRef}
              showTime
              clearable
              onlyTimeSelect
              onChange={handleTimeChange}
              defaultValue={{
                selectValue: 7 * 24 * 60,
                rangePickerVaule: null
              }}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
              {t('common.search')}
            </Button>
            <Button onClick={handleReset}>
              {t('common.reset')}
            </Button>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              onClick={handleExport}
              disabled={selectedRowKeys.length === 0}
            >
            </Button>
          </Space>
        </div>
        
        <CustomTable
          columns={columns}
          dataSource={logs}
          loading={loading}
          rowKey="id"
          rowSelection={rowSelection}
          scroll={{ x: '100%', y: 'calc(100vh - 320px)' }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showQuickJumper: true,
            onChange: handleTableChange,
            onShowSizeChange: handleTableChange
          }}
        />
      </Space>

      <OperateModal
        title={t('system.security.exportTitle')}
        open={exportModalVisible}
        onOk={handleExportConfirm}
        onCancel={handleExportCancel}
        okText={t('system.security.export')}
        cancelText={t('common.cancel')}
        confirmLoading={exporting}
      >
        <Space direction="vertical" className="w-full" size="middle">
          <div>
            <div className="mb-2">{t('system.security.selectFormat')}:</div>
            <Checkbox.Group
              value={exportFormats}
              onChange={(values) => setExportFormats(values as string[])}
            >
              <Space direction="vertical">
                <Checkbox value="excel">Excel (.xlsx)</Checkbox>
                <Checkbox value="csv">CSV (.csv)</Checkbox>
              </Space>
            </Checkbox.Group>
          </div>
        </Space>
      </OperateModal>

      {exporting && (
        <div className="fixed bottom-5 left-5 w-[300px] p-4 bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg shadow-md z-[1000]">
          <div className="mb-2 text-xs">{t('system.security.exporting')}</div>
          <Progress percent={exportProgress} status="active" />
        </div>
      )}
    </div>
  );
};

export default UserLoginLogs;
