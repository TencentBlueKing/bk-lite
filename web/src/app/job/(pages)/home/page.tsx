'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { Button, Tag } from 'antd';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import CustomTable from '@/components/custom-table';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import { JobRecord, JobRecordStatus, JobRecordSource } from '@/app/job/types';

const STATUS_COLOR_MAP: Record<JobRecordStatus, string> = {
  pending: '#faad14',
  running: '#1890ff',
  success: '#52c41a',
  failed: '#ff4d4f',
  canceled: '#8c8c8c',
};

const getSourceConfig = (source: JobRecordSource | string | undefined) => {
  const configs: Record<string, { color: string; bg: string; border: string }> = {
    manual: { color: '#2d87ff', bg: 'rgba(45, 135, 255, 0.08)', border: '#2d87ff' },
    scheduled: { color: '#ff6600', bg: 'rgba(255, 102, 0, 0.08)', border: '#ff6600' },
    api: { color: '#722ed1', bg: 'rgba(114, 46, 209, 0.08)', border: '#722ed1' },
  };
  return configs[source || 'manual'] || configs.manual;
};

const JobHomePage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const { isLoading: isApiReady } = useApiClient();
  const { getJobRecordList } = useJobApi();

  const [recentJobs, setRecentJobs] = useState<JobRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const cardColors = [
    { bg: 'rgba(45, 135, 255, 0.08)', icon: '#2d87ff' },
    { bg: 'rgba(45, 199, 165, 0.08)', icon: '#2dc7a5' },
    { bg: 'rgba(255, 156, 60, 0.08)', icon: '#ff9c3c' },
  ];

  const featureCards = [
    {
      key: 'script',
      icon: 'wenbenfenlei',
      title: t('job.scriptExecution'),
      description: t('job.scriptExecutionDesc'),
      link: '/job/execution/quick-exec',
    },
    {
      key: 'file',
      icon: 'shitishu',
      title: t('job.fileDistribution'),
      description: t('job.fileDistributionDesc'),
      link: '/job/execution/file-dist',
    },
    {
      key: 'cron',
      icon: 'shixuyuce',
      title: t('job.scheduledTask'),
      description: t('job.scheduledTaskDesc'),
      link: '/job/execution/cron-task',
    },
  ];

  const fetchRecentJobs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getJobRecordList({ page: 1, page_size: 20 });
      setRecentJobs(res.items || res.results || []);
    } catch {
      setRecentJobs([]);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isApiReady) {
      fetchRecentJobs();
    }
  }, [isApiReady, fetchRecentJobs]);

  const formatTime = (timeStr: string | null | undefined) => {
    if (!timeStr) return '-';
    const d = new Date(timeStr);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const getStatusText = (status: JobRecordStatus) => {
    const statusTextMap: Record<JobRecordStatus, string> = {
      pending: t('job.statusPending'),
      running: t('job.statusRunning'),
      success: t('job.statusSuccess'),
      failed: t('job.statusFailed'),
      canceled: t('job.statusCanceled'),
    };
    return statusTextMap[status] || status;
  };

  const getSourceText = (source: JobRecordSource | undefined) => {
    if (!source) return '-';
    const sourceTextMap: Record<JobRecordSource, string> = {
      manual: t('job.manual'),
      scheduled: t('job.scheduled'),
      api: 'API',
    };
    return sourceTextMap[source] || source;
  };

  const handleViewDetail = (record: JobRecord) => {
    router.push(`/job/execution/job-record?id=${record.id}`);
  };

  const recentJobColumns = [
    {
      title: t('job.jobName'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: t('job.jobType'),
      dataIndex: 'job_type_display',
      key: 'job_type_display',
      width: 120,
      render: (text: string) => (
        <Tag
          style={{
            color: 'var(--color-text-3)',
            backgroundColor: 'var(--color-bg)',
            borderColor: 'var(--color-border-1)',
            margin: 0,
          }}
        >
          {text}
        </Tag>
      ),
    },
    {
      title: t('job.triggerSource'),
      dataIndex: 'trigger_source',
      key: 'trigger_source',
      width: 120,
      render: (_: unknown, record: JobRecord) => {
        const source = record.trigger_source || record.source;
        const display = record.trigger_source_display || record.source_display;
        const style = getSourceConfig(source);
        return (
          <Tag
            style={{
              color: style.color,
              backgroundColor: style.bg,
              borderColor: style.border,
              margin: 0,
            }}
          >
            {display || getSourceText(source as JobRecordSource)}
          </Tag>
        );
      },
    },
    {
      title: t('job.executionStatus'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (_: unknown, record: JobRecord) => {
        const color = STATUS_COLOR_MAP[record.status] || '#8c8c8c';
        return (
          <Tag
            style={{
              color,
              backgroundColor: `${color}10`,
              borderColor: color,
              margin: 0,
            }}
          >
            {record.status_display || getStatusText(record.status)}
          </Tag>
        );
      },
    },
    {
      title: t('job.startTime'),
      dataIndex: 'started_at',
      key: 'started_at',
      width: 180,
      render: (_: unknown, record: JobRecord) => formatTime(record.started_at),
    },
    {
      title: t('job.operation'),
      key: 'action',
      width: 100,
      render: (_: unknown, record: JobRecord) => (
        <a
          className="text-[var(--color-primary)] cursor-pointer"
          onClick={() => handleViewDetail(record)}
        >
          {t('job.viewDetail')}
        </a>
      ),
    },
  ];

  return (
    <div className="w-full">
      {/* Feature Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        {featureCards.map((card, index) => (
          <div
            key={card.key}
            className="bg-[var(--color-bg)] rounded-lg p-6 shadow-sm border border-[var(--color-border-1)] flex h-full flex-col"
          >
            <div
              className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
              style={{ backgroundColor: cardColors[index].bg }}
            >
              <Icon
                type={card.icon}
                className="text-2xl"
                style={{ color: cardColors[index].icon }}
              />
            </div>
            <h3 className="text-base font-semibold mb-2">{card.title}</h3>
            <p className="text-sm text-[var(--color-text-3)] leading-relaxed mb-6">
              {card.description}
            </p>
            <div className="mt-auto">
              <Button
                type="primary"
                block
                onClick={() => router.push(card.link)}
              >
                {t('job.enter')}
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* Recent Jobs Table */}
      <div className="bg-[var(--color-bg)] rounded-lg p-6 shadow-sm border border-[var(--color-border-1)]">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold">{t('job.recentJobs')}</h3>
          <a
            className="text-sm text-[var(--color-primary)] cursor-pointer"
            onClick={() => router.push('/job/execution/job-record')}
          >
            {t('job.viewAll')} →
          </a>
        </div>
        <CustomTable
          columns={recentJobColumns}
          dataSource={recentJobs}
          loading={loading}
          rowKey="id"
          pagination={false}
          size="middle"
        />
      </div>
    </div>
  );
};

export default JobHomePage;
