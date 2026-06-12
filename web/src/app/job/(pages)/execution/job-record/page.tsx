'use client';

import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import {
  Tag,
  Segmented,
  Button,
  Spin,
  message,
  Input,
  Drawer,
  DatePicker,
  Tabs,
  Table,
  Empty,
  Modal,
  Alert,
} from 'antd';
import {
  ArrowLeftOutlined,
  CopyOutlined,
  FileTextOutlined,
  EditOutlined,
  ReloadOutlined,
  SearchOutlined,
  DownloadOutlined,
  ArrowDownOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  FolderOutlined,
  FileOutlined,
  ProfileOutlined,
} from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import MarkdownRenderer from '@/components/markdown';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { useAuth } from '@/context/auth';
import useJobApi from '@/app/job/api';
import { useExecutionStream } from '@/app/job/hooks/useExecutionStream';
import { JobRecord, JobRecordStatus, JobRecordSource, JobRecordDetail, ExecutionTarget, Playbook, FileTreeNode, PlaybookFilePreview } from '@/app/job/types';
import { ColumnItem } from '@/types';
import SearchCombination from '@/components/search-combination';
import { SearchFilters, FieldConfig } from '@/components/search-combination/types';
import { useRouter, useSearchParams } from 'next/navigation';
import dayjs, { Dayjs } from 'dayjs';

const { RangePicker } = DatePicker;
const QUICK_EXEC_REPLAY_STORAGE_KEY = 'job.quick-exec.replay';
const FILE_DIST_REPLAY_STORAGE_KEY = 'job.file-dist.replay';

const JobRecordPage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const recordId = searchParams.get('id');
  const { isLoading: isApiReady } = useApiClient();
  const { getJobRecordList, getJobRecordDetail, getPlaybookDetail, previewPlaybookFile } = useJobApi();

  // List state
  const [data, setData] = useState<JobRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchFilters, setSearchFilters] = useState<SearchFilters>({});
  const [timeRange, setTimeRange] = useState<'today' | '7days' | '30days' | 'custom'>('today');
  const [customRange, setCustomRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  // Detail state
  const [detail, setDetail] = useState<JobRecordDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedTargetId, setSelectedTargetId] = useState<number | null>(null);
  const [logSearch, setLogSearch] = useState('');
  const [autoScroll, setAutoScroll] = useState(false);
  const [scriptDrawerOpen, setScriptDrawerOpen] = useState(false);
  const [playbookDrawerOpen, setPlaybookDrawerOpen] = useState(false);
  const [viewingPlaybook, setViewingPlaybook] = useState<Playbook | null>(null);
  const [playbookDetailLoading, setPlaybookDetailLoading] = useState(false);
  const [filePreviewModalOpen, setFilePreviewModalOpen] = useState(false);
  const [filePreviewLoading, setFilePreviewLoading] = useState(false);
  const [filePreviewData, setFilePreviewData] = useState<PlaybookFilePreview | null>(null);
  const [filePreviewError, setFilePreviewError] = useState<string | null>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);

  const formatFilterTime = useCallback((value: Dayjs) => value.format('YYYY-MM-DD HH:mm:ss'), []);

  const getTimeFilter = useCallback(() => {
    const now = dayjs();
    switch (timeRange) {
      case 'today':
        return {
          created_at_after: formatFilterTime(now.startOf('day')),
          created_at_before: formatFilterTime(now.endOf('day')),
        };
      case '7days':
        return {
          created_at_after: formatFilterTime(now.subtract(7, 'day')),
          created_at_before: formatFilterTime(now),
        };
      case '30days':
        return {
          created_at_after: formatFilterTime(now.subtract(30, 'day')),
          created_at_before: formatFilterTime(now),
        };
      case 'custom':
        if (!customRange) {
          return {};
        }
        return {
          created_at_after: formatFilterTime(customRange[0].startOf('day')),
          created_at_before: formatFilterTime(customRange[1].endOf('day')),
        };
      default:
        return {};
    }
  }, [customRange, formatFilterTime, timeRange]);

  const fetchData = useCallback(
    async (params: { filters?: SearchFilters; current?: number; pageSize?: number } = {}) => {
      setLoading(true);
      try {
        const filters = params.filters ?? searchFilters;
        const timeFilter = getTimeFilter();
        const queryParams: Record<string, unknown> = {
          page: params.current ?? pagination.current,
          page_size: params.pageSize ?? pagination.pageSize,
          ...timeFilter,
        };
        if (filters && Object.keys(filters).length > 0) {
          Object.entries(filters).forEach(([field, conditions]) => {
            conditions.forEach((condition) => {
              if (condition.lookup_expr === 'in' && Array.isArray(condition.value)) {
                queryParams[field] = (condition.value as string[]).join(',');
              } else {
                queryParams[field] = condition.value;
              }
            });
          });
        }
        const res = await getJobRecordList(queryParams as any);
        setData(res.items || res.results || []);
        setPagination((prev) => ({
          ...prev,
          total: res.count || 0,
        }));
      } finally {
        setLoading(false);
      }
    },
    [searchFilters, pagination.current, pagination.pageSize, getTimeFilter]
  );

  const fetchDetail = useCallback(async (id: number, silent = false) => {
    if (!silent) {
      setDetailLoading(true);
    }
    try {
      const res = await getJobRecordDetail(id);

      // 兼容 API 返回的 execution_results 字段，映射为 execution_targets
      if ((!res.execution_targets || res.execution_targets.length === 0) && res.execution_results?.length) {
        res.execution_targets = res.execution_results.map((result: any, index: number) => ({
          id: index,
          target: index,
          target_key: result.target_key != null ? String(result.target_key) : undefined,
          target_name: result.name || result.ip,
          target_ip: result.ip,
          status: result.status,
          status_display: result.status,
          stdout: result.stdout || '',
          stderr: result.stderr || result.error_message || '',
          exit_code: result.exit_code,
          started_at: result.started_at,
          finished_at: result.finished_at,
          error_message: result.error_message || '',
        }));
      }

      // 任务刚创建时可能还没有 execution_results，但 target_list 已经存在
      if ((!res.execution_targets || res.execution_targets.length === 0) && res.target_list?.length) {
        res.execution_targets = res.target_list.map((target: any, index: number) => ({
          id: Number(target.target_id || target.node_id || index),
          target: Number(target.target_id || target.node_id || index),
          target_key: String(target.node_id || target.target_id || index),
          target_name: target.name || target.ip || `Target ${index + 1}`,
          target_ip: target.ip || '-',
          status: res.status,
          status_display: res.status_display || res.status,
          stdout: '',
          stderr: '',
          exit_code: 0,
          started_at: res.started_at || null,
          finished_at: res.finished_at || null,
          error_message: '',
        }));
      }

      setDetail(res);
    } finally {
      if (!silent) {
        setDetailLoading(false);
      }
    }
  }, [getJobRecordDetail]);

  const handleReExecute = useCallback(async () => {
    if (!detail) return;

    const isFileDistributionJob =
      detail.job_type === 'file' ||
      !!detail.target_path ||
      !!detail.files?.length;

    const mappedHosts = ((detail.target_list as Array<{ target_id?: number; node_id?: string; name?: string; ip?: string; os?: string }> | undefined) || []).map((target) => ({
      key: String(target.target_id || target.node_id || ''),
      hostName: target.name || '',
      ipAddress: target.ip || '',
      cloudRegion: '-',
      osType: target.os || '-',
      currentDriver: '-',
    }));

    if (isFileDistributionJob) {
      const fileReplayPayload = {
        jobName: detail.name,
        timeout: String(detail.timeout || 600),
        targetSource: (detail as any).target_source === 'node_mgmt' ? 'node_manager' : 'target_manager',
        selectedHosts: mappedHosts,
        targetPath: detail.target_path || '',
        overwriteStrategy: (detail as any).overwrite_strategy || 'overwrite',
        files: detail.files || [],
      };

      if (typeof window !== 'undefined') {
        window.sessionStorage.setItem(FILE_DIST_REPLAY_STORAGE_KEY, JSON.stringify(fileReplayPayload));
      }

      router.push('/job/execution/file-dist?mode=reexecute');
      return;
    }

    const replayPayload = {
      jobName: detail.name,
      timeout: String(detail.timeout || 600),
      targetSource: (detail as any).target_source === 'node_mgmt' ? 'node_manager' : 'target_manager',
      selectedHosts: mappedHosts,
      templateType: detail.playbook ? 'playbook' : 'scriptLibrary',
      scriptId: detail.script,
      playbookId: detail.playbook,
      params: detail.params || {},
      scriptType: detail.script_type,
      scriptContent: detail.script_content,
    };

    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem(QUICK_EXEC_REPLAY_STORAGE_KEY, JSON.stringify(replayPayload));
    }

    if (detail.playbook) {
      router.push(`/job/execution/quick-exec?playbook_id=${detail.playbook}&mode=reexecute`);
      return;
    }

    if (detail.script) {
      router.push(`/job/execution/quick-exec?script_id=${detail.script}&mode=reexecute`);
      return;
    }

    router.push('/job/execution/quick-exec?mode=reexecute');
  }, [detail, router]);

  const handleOpenPlaybook = useCallback(async () => {
    if (!detail?.playbook) {
      return;
    }

    setPlaybookDrawerOpen(true);
    setPlaybookDetailLoading(true);
    try {
      const playbookDetail = await getPlaybookDetail(detail.playbook);
      setViewingPlaybook(playbookDetail);
    } catch {
      message.error(t('job.loadPlaybookDetailFailed'));
      setPlaybookDrawerOpen(false);
    } finally {
      setPlaybookDetailLoading(false);
    }
  }, [detail?.playbook, getPlaybookDetail, t]);

  useEffect(() => {
    if (!isApiReady) {
      if (recordId) {
        fetchDetail(Number(recordId));
      } else {
        fetchData();
      }
    }
  }, [isApiReady, timeRange, customRange, recordId]);

  useEffect(() => {
    if (!isApiReady && !recordId) {
      fetchData();
    }
  }, [pagination.current, pagination.pageSize]);

  // Auto-refresh polling for in-progress job details
  useEffect(() => {
    // Only poll when viewing detail and status is pending or running
    if (!recordId || !detail?.status) {
      return;
    }
    
    if (detail.status !== 'pending' && detail.status !== 'running') {
      // Clear any existing timer when status becomes terminal
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
      return;
    }
    
    // Start polling every 5 seconds (silent mode - no loading spinner)
    pollingTimerRef.current = setInterval(() => {
      fetchDetail(Number(recordId), true);
    }, 5000);
    
    return () => {
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
    };
  }, [detail?.status, recordId, fetchDetail]);

  const handleSearchChange = useCallback((filters: SearchFilters) => {
    setSearchFilters(filters);
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ filters, current: 1 });
  }, [fetchData]);

  const handleTableChange = (pag: any) => {
    setPagination(pag);
  };

  const handleViewDetail = (record: JobRecord) => {
    router.push(`/job/execution/job-record?id=${record.id}`);
  };

  const handleBack = () => {
    router.push('/job/execution/job-record');
  };

  const formatDuration = (duration: number | null | undefined): string => {
    if (duration === null || duration === undefined) return '-';
    if (duration < 60) return `${duration}s`;
    const minutes = Math.floor(duration / 60);
    const seconds = duration % 60;
    if (minutes < 60) return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const remainMinutes = minutes % 60;
    return `${hours}h ${remainMinutes}m`;
  };

  const getStatusConfig = (status: JobRecordStatus) => {
    const configs: Record<JobRecordStatus, { color: string; label: string }> = {
      pending: { color: 'default', label: t('job.statusPending') },
      running: { color: 'processing', label: t('job.statusRunning') },
      success: { color: 'success', label: t('job.statusSuccess') },
      failed: { color: 'error', label: t('job.statusFailed') },
      canceled: { color: 'warning', label: t('job.statusCanceled') },
    };
    return configs[status] || configs.pending;
  };

  const getSourceConfig = (source: JobRecordSource | string | undefined) => {
    const configs: Record<string, { color: string; label: string }> = {
      manual: { color: 'blue', label: t('job.manual') },
      scheduled: { color: 'orange', label: t('job.scheduled') },
      api: { color: 'default', label: 'API' },
    };
    return configs[source || 'manual'] || configs.manual;
  };

  const fieldConfigs: FieldConfig[] = useMemo(() => [
    {
      name: 'name',
      label: t('job.jobName'),
      lookup_expr: 'icontains',
    },
    {
      name: 'job_type',
      label: t('job.jobType'),
      lookup_expr: 'in',
      options: [
        { id: 'script', name: t('job.scriptExecution') },
        { id: 'playbook', name: t('job.playbook') },
        { id: 'file', name: t('job.fileDistribution') },
      ],
    },
    {
      name: 'trigger_source',
      label: t('job.triggerSource'),
      lookup_expr: 'in',
      options: [
        { id: 'manual', name: t('job.manual') },
        { id: 'scheduled', name: t('job.scheduled') },
        { id: 'api', name: t('job.api') },
      ],
    },
    {
      name: 'status',
      label: t('job.executionStatus'),
      lookup_expr: 'in',
      options: [
        { id: 'pending', name: t('job.statusPending') },
        { id: 'running', name: t('job.statusRunning') },
        { id: 'success', name: t('job.statusSuccess') },
        { id: 'failed', name: t('job.statusFailed') },
        { id: 'canceled', name: t('job.statusCanceled') },
      ],
    },
    {
      name: 'created_by',
      label: t('job.initiator'),
      lookup_expr: 'icontains',
    },
  ], [t]);

  const columns: ColumnItem[] = [
    {
      title: t('job.jobId'),
      dataIndex: 'id',
      key: 'id',
      width: 100,
      render: (value: number) => <span>{`#${value}`}</span>,
    },
    {
      title: t('job.jobName'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: t('job.jobType'),
      dataIndex: 'job_type_display',
      key: 'job_type',
      width: 120,
      render: (text: string, record: JobRecord) => {
        const colorMap: Record<string, string> = {
          script: 'blue',
          playbook: 'purple',
          file: 'green',
        };
        return <Tag color={colorMap[record.job_type] || 'default'}>{text}</Tag>;
      },
    },
    {
      title: t('job.triggerSource'),
      dataIndex: 'trigger_source',
      key: 'trigger_source',
      width: 120,
      render: (_: unknown, record: JobRecord) => {
        const source = record.trigger_source || record.source;
        const config = getSourceConfig(source);
        const label = record.trigger_source_display || record.source_display || config.label;
        return <Tag color={config.color}>{label}</Tag>;
      },
    },
    {
      title: t('job.executionStatus'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (value: JobRecordStatus) => {
        const config = getStatusConfig(value);
        return <Tag color={config.color}>{config.label}</Tag>;
      },
    },
    {
      title: t('job.initiator'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 120,
    },
    {
      title: t('job.startTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) =>
        <span>{text ? dayjs(text).format('YYYY-MM-DD HH:mm:ss') : '-'}</span>,
    },
    {
      title: t('job.duration'),
      dataIndex: 'duration',
      key: 'duration',
      width: 100,
      render: (value: number | null) => <span>{formatDuration(value)}</span>,
    },
    {
      title: t('job.operation'),
      dataIndex: 'action',
      key: 'action',
      fixed: 'right',
      width: 120,
      render: (_: unknown, record: JobRecord) => (
        <a
          className="text-(--color-primary) cursor-pointer"
          onClick={() => handleViewDetail(record)}
        >
          {t('job.viewDetail')}
        </a>
      ),
    },
  ];

  const copyToClipboard = async (text: string) => {
    if (!text) {
      message.warning(t('common.noContentToCopy'));
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      message.success(t('common.copySuccess'));
    } catch {
      // Fallback for older browsers or when clipboard API fails
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-9999px';
      textArea.style.top = '-9999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      try {
        document.execCommand('copy');
        message.success(t('common.copySuccess'));
      } catch {
        message.error(t('common.copyFailed'));
      }
      document.body.removeChild(textArea);
    }
  };

  // Get selected target for detail view
  const rawSelectedTarget = useMemo(() => {
    if (!detail?.execution_targets?.length) return null;
    if (selectedTargetId === null) return detail.execution_targets[0];
    return detail.execution_targets.find(t => t.id === selectedTargetId) || detail.execution_targets[0];
  }, [detail, selectedTargetId]);

  // 实时流式输出：执行中（pending/running）订阅 SSE，按 target 累积 stdout/stderr
  const authContext = useAuth();
  const isExecuting = detail?.status === 'pending' || detail?.status === 'running';
  const { liveOutput, streaming } = useExecutionStream({
    executionId: recordId ? Number(recordId) : null,
    enabled: !!recordId && isExecuting,
    token: authContext?.token || null,
    onAllDone: () => {
      if (recordId) fetchDetail(Number(recordId), true);
    },
  });

  // 用实时输出覆盖选中目标的内容：
  // - 仅执行中（pending/running）覆盖；终态回落到权威 execution_results。
  // - 优先该目标自己的流（SSH/本地按 target_key）；无则回退 ansible 合并流（key='ansible'）。
  const selectedTarget = useMemo(() => {
    if (!rawSelectedTarget) return null;
    if (!isExecuting) return rawSelectedTarget;
    const perTarget = rawSelectedTarget.target_key ? liveOutput[rawSelectedTarget.target_key] : undefined;
    const live = perTarget && (perTarget.stdout || perTarget.stderr) ? perTarget : liveOutput['ansible'];
    if (!live || (!live.stdout && !live.stderr)) return rawSelectedTarget;
    return {
      ...rawSelectedTarget,
      stdout: live.stdout || rawSelectedTarget.stdout,
      stderr: live.stderr || rawSelectedTarget.stderr,
    };
  }, [rawSelectedTarget, liveOutput, isExecuting]);

  // Auto-select first target when detail loads
  useEffect(() => {
    if (detail?.execution_targets?.length && selectedTargetId === null) {
      setSelectedTargetId(detail.execution_targets[0].id);
    }
  }, [detail, selectedTargetId]);

  // Parse and format log lines with timestamps
  const logLines = useMemo(() => {
    if (!selectedTarget?.stdout) return [];
    const lines = selectedTarget.stdout.split('\n').filter(line => line.trim());
    return lines.map((line, index) => ({ index, content: line }));
  }, [selectedTarget]);

  // Filter log lines by search
  const filteredLogLines = useMemo(() => {
    if (!logSearch.trim()) return logLines;
    const searchLower = logSearch.toLowerCase();
    return logLines.filter(line => line.content.toLowerCase().includes(searchLower));
  }, [logLines, logSearch]);

  // Auto-scroll to bottom when enabled and log changes
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [autoScroll, filteredLogLines]);

  // Get last log timestamp
  const lastLogTime = useMemo(() => {
    if (!selectedTarget?.finished_at && !selectedTarget?.started_at) return null;
    return selectedTarget.finished_at || selectedTarget.started_at;
  }, [selectedTarget]);

  // Calculate target duration
  const getTargetDuration = (target: ExecutionTarget): number | null => {
    if (!target.started_at || !target.finished_at) return null;
    return Math.floor((new Date(target.finished_at).getTime() - new Date(target.started_at).getTime()) / 1000);
  };

  // Get script line count
  const scriptLineCount = useMemo(() => {
    if (!detail?.script_content) return 0;
    return detail.script_content.split('\n').length;
  }, [detail?.script_content]);

  // Execution parameters text (脚本执行为按顺序拼接的位置参数字符串)
  const executeParamsText = useMemo(() => {
    const p = detail?.params as unknown;
    if (p === null || p === undefined || p === '') return '';
    if (typeof p === 'string') return p;
    try {
      return JSON.stringify(p);
    } catch {
      return String(p);
    }
  }, [detail?.params]);

  const handlePreviewPlaybookFile = useCallback(async (filePath: string, parentPaths: string[] = []) => {
    if (!viewingPlaybook) {
      return;
    }

    const fullPath = [...parentPaths, filePath].join('/');
    setFilePreviewLoading(true);
    setFilePreviewError(null);
    setFilePreviewData(null);
    setFilePreviewModalOpen(true);

    try {
      const result = await previewPlaybookFile(viewingPlaybook.id, fullPath);
      setFilePreviewData(result);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string }; status?: number } };
      const detailMessage = err?.response?.data?.detail;
      const status = err?.response?.status;

      if (status === 413) {
        setFilePreviewError(t('job.filePreviewTooLarge'));
      } else if (status === 404) {
        setFilePreviewError(t('job.filePreviewNotFound'));
      } else if (detailMessage) {
        setFilePreviewError(detailMessage);
      } else {
        setFilePreviewError(t('job.filePreviewError'));
      }
    } finally {
      setFilePreviewLoading(false);
    }
  }, [previewPlaybookFile, t, viewingPlaybook]);

  const renderPlaybookFileTree = useCallback((nodes: FileTreeNode[], depth = 0, parentPaths: string[] = []) => {
    return nodes.map((node, idx) => (
      <div key={`${depth}-${idx}-${node.name}`}>
        <div
          className="flex items-center justify-between rounded px-2 py-1.5 hover:bg-(--color-fill-2)"
          style={{ paddingLeft: `${depth * 20 + 8}px` }}
        >
          <div className="flex items-center gap-2">
            {node.type === 'directory' ? (
              <FolderOutlined style={{ color: '#faad14' }} />
            ) : (
              <FileOutlined style={{ color: 'var(--color-text-3)' }} />
            )}
            <span className="text-sm" style={{ color: 'var(--color-text-1)' }}>
              {node.name}
            </span>
          </div>
          {node.type === 'file' && (
            <a
              className="cursor-pointer text-sm text-[var(--color-primary)]"
              onClick={() => handlePreviewPlaybookFile(node.name, parentPaths)}
            >
              {t('job.preview')}
            </a>
          )}
        </div>
        {node.type === 'directory' && node.children && renderPlaybookFileTree(node.children, depth + 1, [...parentPaths, node.name])}
      </div>
    ));
  }, [handlePreviewPlaybookFile, t]);

  const playbookViewTabs = useMemo(() => {
    if (!viewingPlaybook) {
      return [];
    }

    const basicInfoItems = [
      { label: t('job.executionVersion'), value: detail?.playbook ? (detail.playbook_version || '-') : null },
      { label: t('job.playbookName'), value: viewingPlaybook.name },
      { label: t('job.playbookDescription'), value: viewingPlaybook.description || '-' },
      { label: t('job.currentVersion'), value: viewingPlaybook.version || '-' },
      { label: t('job.recentUpdateTime'), value: viewingPlaybook.updated_at ? dayjs(viewingPlaybook.updated_at).format('YYYY-MM-DD HH:mm:ss') : '-' },
      { label: t('job.uploader'), value: viewingPlaybook.created_by || '-' },
    ].filter((item): item is { label: string; value: string | null } => item.value !== null);

    return [
      {
        key: 'basicInfo',
        label: t('job.basicInfoTab'),
        children: (
          <div className="space-y-4 py-2">
            {basicInfoItems.map((item, idx) => (
              <div key={idx} className="flex">
                <span
                  className="w-32 shrink-0 text-sm"
                  style={{ color: 'var(--color-text-3)' }}
                >
                  {item.label}
                </span>
                <span className="text-sm" style={{ color: 'var(--color-text-1)' }}>
                  {item.value}
                </span>
              </div>
            ))}
          </div>
        ),
      },
      {
        key: 'params',
        label: t('job.paramsDescriptionTab'),
        children:
          viewingPlaybook.params && viewingPlaybook.params.length > 0 ? (
            <Table
              dataSource={viewingPlaybook.params}
              rowKey="name"
              pagination={false}
              size="small"
              columns={[
                {
                  title: t('job.parameterName'),
                  dataIndex: 'name',
                  key: 'name',
                  render: (text: string) => (
                    <span className="font-mono text-[var(--color-primary)]">{text}</span>
                  ),
                },
                {
                  title: t('job.defaultVal'),
                  dataIndex: 'default',
                  key: 'default',
                  render: (text: string) => text || '-',
                },
                {
                  title: t('job.paramDesc'),
                  dataIndex: 'description',
                  key: 'description',
                  render: (text: string) => text || '-',
                },
              ]}
            />
          ) : (
            <Empty description={t('job.noParams')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ),
      },
      {
        key: 'fileList',
        label: t('job.fileListTab'),
        children:
          viewingPlaybook.file_list && viewingPlaybook.file_list.length > 0 ? (
            <div
              className="rounded-md border p-2"
              style={{ borderColor: 'var(--color-border-1)' }}
            >
              {renderPlaybookFileTree(viewingPlaybook.file_list)}
            </div>
          ) : (
            <Empty description={t('job.noFiles')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ),
      },
      {
        key: 'readme',
        label: t('job.readmeTab'),
        children: viewingPlaybook.readme ? (
          <MarkdownRenderer content={viewingPlaybook.readme} />
        ) : (
          <Empty description={t('job.noReadme')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ),
      },
    ];
  }, [detail?.playbook, detail?.playbook_version, renderPlaybookFileTree, t, viewingPlaybook]);

  // Download log as file
  const handleDownloadLog = () => {
    const content = selectedTarget?.stdout || selectedTarget?.stderr || '';
    if (!content) return;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${detail?.name || 'job'}_${selectedTarget?.target_name || 'target'}_log.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Highlight log keywords
  const highlightLog = (content: string) => {
    // Match timestamp at start: HH:mm:ss or YYYY-MM-DD HH:mm:ss
    const timestampMatch = content.match(/^(\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*/);
    let timestamp = '';
    let rest = content;
    if (timestampMatch) {
      timestamp = timestampMatch[0];
      rest = content.slice(timestampMatch[0].length);
    }

    // Determine color based on keywords
    let colorClass = 'text-gray-300';
    if (rest.includes('[SUCCESS]') || rest.includes('[EXIT]') || rest.includes('成功')) {
      colorClass = 'text-green-400';
    } else if (rest.includes('[ERROR]') || rest.includes('[FAIL]') || rest.includes('失败')) {
      colorClass = 'text-red-400';
    } else if (rest.includes('[WARN]') || rest.includes('[WARNING]')) {
      colorClass = 'text-yellow-400';
    } else if (rest.includes('[INFO]')) {
      colorClass = 'text-gray-300';
    }

    return (
      <>
        {timestamp && <span className="text-gray-500">{timestamp}</span>}
        <span className={colorClass}>{rest}</span>
      </>
    );
  };

  // Render detail view
  if (recordId) {
    if (detailLoading) {
      return (
        <div className="w-full h-full flex items-center justify-center">
          <Spin size="large" />
        </div>
      );
    }

    if (!detail) {
      return (
        <div className="w-full h-full flex items-center justify-center">
          <span>{t('common.noData')}</span>
        </div>
      );
    }

    return (
      <div className="w-full h-full flex flex-col overflow-hidden">
        {/* Header Card */}
        <div
          className="mb-4 rounded-lg px-6 py-4 shrink-0"
          style={{
            background: 'var(--color-bg-1)',
            border: '1px solid var(--color-border-1)',
          }}
        >
          {/* Title Row */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Button
                type="text"
                icon={<ArrowLeftOutlined />}
                onClick={handleBack}
                className="p-1!"
              />
              <h2
                className="text-lg font-medium m-0"
                style={{ color: 'var(--color-text-1)' }}
              >
                {detail.name}
              </h2>
              <span className="text-sm" style={{ color: 'var(--color-text-3)' }}>
                #{detail.id}
              </span>
              <Tag color={getStatusConfig(detail.status).color}>
                {getStatusConfig(detail.status).label}
              </Tag>
            </div>
            <div className="flex items-center gap-2">
              <Button
                icon={<ReloadOutlined />}
                onClick={handleReExecute}
              >
                {t('job.reExecute')}
              </Button>
            </div>
          </div>

          {/* Meta Info Row */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6 flex-wrap text-sm">
              <div>
                <span style={{ color: 'var(--color-text-3)' }}>{t('job.jobType')}</span>
                <span className="ml-2" style={{ color: 'var(--color-text-1)' }}>
                  {detail.job_type_display}
                </span>
              </div>
              <div>
                <span style={{ color: 'var(--color-text-3)' }}>{t('job.triggerSource')}</span>
                <Tag color={getSourceConfig(detail.trigger_source || detail.source).color} className="ml-2">
                  {detail.trigger_source_display || detail.source_display || '-'}
                </Tag>
              </div>
              <div>
                <span style={{ color: 'var(--color-text-3)' }}>{t('job.initiator')}</span>
                <span className="ml-2" style={{ color: 'var(--color-text-1)' }}>
                  {detail.created_by}
                </span>
              </div>
              <div>
                <span style={{ color: 'var(--color-text-3)' }}>{t('job.startTime')}</span>
                <span className="ml-2" style={{ color: 'var(--color-text-1)' }}>
                  {detail.started_at ? dayjs(detail.started_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
                </span>
              </div>
              <div>
                <span style={{ color: 'var(--color-text-3)' }}>{t('job.duration')}</span>
                <span className="ml-2" style={{ color: 'var(--color-text-1)' }}>
                  {formatDuration(detail.duration)}
                </span>
              </div>
              <div>
                <span style={{ color: 'var(--color-text-3)' }}>{t('job.targetHosts')}</span>
                <span className="ml-2" style={{ color: 'var(--color-text-1)' }}>
                  {detail.total_count || detail.target_count || 0} {t('job.hostsUnit')}
                </span>
              </div>
              {detail.executor_user && (
                <div>
                  <span style={{ color: 'var(--color-text-3)' }}>{t('job.executeUser')}</span>
                  <span className="ml-2" style={{ color: 'var(--color-text-1)' }}>
                    {detail.executor_user}
                  </span>
                </div>
              )}
              <div>
                <span style={{ color: 'var(--color-text-3)' }}>{t('job.timeout')}</span>
                <span className="ml-2" style={{ color: 'var(--color-text-1)' }}>
                  {detail.timeout || 300}{t('job.seconds')}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {detail.playbook && (
                <Button icon={<FileTextOutlined />} onClick={handleOpenPlaybook}>
                  {t('job.viewVersion')}
                </Button>
              )}
              {detail.job_type === 'script' && detail.script_content && (
                <Button
                  icon={<FileTextOutlined />}
                  onClick={() => setScriptDrawerOpen(true)}
                >
                  {t('job.viewScriptBtn')}
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Main Content: Host List + Log Panel */}
        <div className="flex gap-4 flex-1 min-h-0">
          {/* Left: Target Host List */}
          <div
            className="flex w-80 shrink-0 flex-col rounded-lg"
            style={{
              background: 'var(--color-bg-1)',
              border: '1px solid var(--color-border-1)',
            }}
          >
            {/* Host List Header */}
            <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--color-border-1)' }}>
              <div className="flex items-center justify-between">
                <span className="font-medium" style={{ color: 'var(--color-text-1)' }}>
                  {t('job.targetHosts')}
                </span>
                <div className="flex items-center gap-2 text-sm">
                  <span className="flex items-center gap-1 text-green-500">
                    <CheckCircleFilled />
                    {detail.success_count}
                  </span>
                  <span className="flex items-center gap-1 text-red-500">
                    <CloseCircleFilled />
                    {detail.failed_count}
                  </span>
                </div>
              </div>
            </div>

            {/* Host List */}
            <div className="flex-1 overflow-auto">
              {detail.execution_targets?.map((target) => {
                const isSelected = selectedTargetId === target.id;
                const duration = getTargetDuration(target);
                return (
                  <div
                    key={target.id}
                    className={`cursor-pointer border-b px-4 py-3 transition-colors ${
                      isSelected ? 'bg-(--color-primary-bg)' : 'hover:bg-(--color-fill-2)'
                    }`}
                    style={{ borderColor: 'var(--color-border-1)' }}
                    onClick={() => setSelectedTargetId(target.id)}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-medium" style={{ color: 'var(--color-text-1)' }}>
                          {target.target_name}
                        </div>
                        <div className="text-xs mt-1" style={{ color: 'var(--color-text-3)' }}>
                          {target.target_ip}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-sm" style={{ color: 'var(--color-text-3)' }}>
                          {duration !== null ? `${duration}s` : '-'}
                        </span>
                        <Tag
                          color={getStatusConfig(target.status).color}
                          className="m-0"
                        >
                          {getStatusConfig(target.status).label}
                        </Tag>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right: Execution Log Panel */}
          <div
            className="flex-1 rounded-lg flex flex-col min-w-0"
            style={{
              background: 'var(--color-bg-1)',
              border: '1px solid var(--color-border-1)',
            }}
          >
            {/* Log Header */}
            <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: 'var(--color-border-1)' }}>
              <div className="flex items-center gap-2">
                <span className="font-medium" style={{ color: 'var(--color-text-1)' }}>
                  {t('job.executionLog')}
                </span>
                {streaming && (
                  <Tag color="processing" className="m-0">
                    <span className="inline-block w-2 h-2 rounded-full bg-current mr-1 animate-pulse align-middle" />
                    {t('job.streamingLive')}
                  </Tag>
                )}
                {selectedTarget && (
                  <span className="text-sm" style={{ color: 'var(--color-text-3)' }}>
                    {selectedTarget.target_name} ({selectedTarget.target_ip})
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Input
                  placeholder={t('job.searchLog')}
                  suffix={<SearchOutlined style={{ color: 'var(--color-text-3)' }} />}
                  value={logSearch}
                  onChange={(e) => setLogSearch(e.target.value)}
                  className="w-48"
                  allowClear
                />
                <Button
                  type={autoScroll ? 'primary' : 'default'}
                  icon={<ArrowDownOutlined />}
                  onClick={() => setAutoScroll(!autoScroll)}
                  title={t('job.autoScroll')}
                />
                <Button
                  icon={<CopyOutlined />}
                  onClick={() => {
                    const content = selectedTarget?.stdout || selectedTarget?.stderr || '';
                    copyToClipboard(content);
                  }}
                  title={t('common.copy')}
                />
                <Button
                  icon={<DownloadOutlined />}
                  onClick={handleDownloadLog}
                  title={t('common.download')}
                />
              </div>
            </div>

            {/* Log Content */}
            <div
              ref={logContainerRef}
              className="flex-1 overflow-auto p-4 font-mono text-sm leading-6"
              style={{ background: '#1e1e1e' }}
            >
              {filteredLogLines.length > 0 ? (
                filteredLogLines.map((line) => (
                  <div key={line.index} className="whitespace-pre-wrap break-all">
                    {highlightLog(line.content)}
                  </div>
                ))
              ) : selectedTarget?.stderr ? (
                <div className="text-red-400 whitespace-pre-wrap">
                  {selectedTarget.stderr}
                </div>
              ) : (
                <div className="text-gray-500">{t('common.noData')}</div>
              )}
            </div>

            {/* Log Footer */}
            <div
              className="px-4 py-2 border-t flex items-center justify-between text-xs"
              style={{
                borderColor: 'var(--color-border-1)',
                color: 'var(--color-text-3)',
              }}
            >
              <span>
                {t('job.totalLines').replace('{count}', String(filteredLogLines.length))}
              </span>
              {lastLogTime && (
                <span>
                  {t('job.lastUpdate')}: {dayjs(lastLogTime).format('HH:mm:ss')}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Script Detail Drawer */}
        <Drawer
          title={t('job.scriptDetail')}
          placement="right"
          width={720}
          open={scriptDrawerOpen}
          onClose={() => setScriptDrawerOpen(false)}
          styles={{
            body: {
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              padding: 24,
            },
          }}
        >
          <div
            className="rounded-lg mb-4 shrink-0"
            style={{
              background: 'var(--color-bg-1)',
              border: '1px solid var(--color-border-1)',
            }}
          >
            <div
              className="px-4 py-3 flex items-center gap-2"
              style={{ borderBottom: '1px solid var(--color-border-1)' }}
            >
              <FileTextOutlined style={{ color: 'var(--color-primary)' }} />
              <span className="font-medium" style={{ color: 'var(--color-text-1)' }}>
                {t('job.scriptInfo')}
              </span>
            </div>
            <div className="p-4">
              <div className="grid grid-cols-2 gap-y-4 text-sm">
                <div>
                  <div className="mb-1" style={{ color: 'var(--color-text-3)' }}>{t('job.contentSource')}</div>
                  <div style={{ color: 'var(--color-text-1)' }}>{t('job.manualInput')}</div>
                </div>
                <div>
                  <div className="mb-1" style={{ color: 'var(--color-text-3)' }}>{t('job.scriptLanguage')}</div>
                  <div style={{ color: 'var(--color-text-1)' }}>
                    {detail.script_type_display || detail.script_type || 'Shell (Bash)'}
                  </div>
                </div>
                <div>
                  <div className="mb-1" style={{ color: 'var(--color-text-3)' }}>{t('job.executeUser')}</div>
                  <div style={{ color: 'var(--color-text-1)' }}>{t('job.defaultExecuteUser')}</div>
                </div>
                <div>
                  <div className="mb-1" style={{ color: 'var(--color-text-3)' }}>{t('job.codeLines')}</div>
                  <div style={{ color: 'var(--color-text-1)' }}>
                    {scriptLineCount} {t('job.lines')}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div
            className="rounded-lg overflow-hidden flex-1 min-h-0 flex flex-col"
            style={{
              background: 'var(--color-bg-1)',
              border: '1px solid var(--color-border-1)',
            }}
          >
            <div
              className="px-4 py-3 flex items-center justify-between shrink-0"
              style={{ borderBottom: '1px solid var(--color-border-1)' }}
            >
              <div className="flex items-center gap-2">
                <EditOutlined style={{ color: 'var(--color-primary)' }} />
                <span className="font-medium" style={{ color: 'var(--color-text-1)' }}>
                  {t('job.scriptContent')}
                </span>
              </div>
              <Button
                type="text"
                size="small"
                icon={<CopyOutlined />}
                onClick={() => copyToClipboard(detail.script_content || '')}
              >
                {t('common.copy')}
              </Button>
            </div>
            <pre
              className="p-0 text-sm overflow-auto font-mono m-0 flex-1 min-h-0"
              style={{
                background: '#1e1e1e',
              }}
            >
              {detail.script_content?.split('\n').map((line, index) => (
                <div key={index} className="flex px-4 py-0.5 leading-6">
                  <span
                    className="mr-4 w-8 shrink-0 select-none text-right"
                    style={{ color: '#6e7681' }}
                  >
                    {index + 1}
                  </span>
                  <code
                    className="flex-1"
                    style={{ color: line.trim().startsWith('#') ? '#6a9955' : line.includes('echo') || line.includes('find') ? '#569cd6' : '#ce9178' }}
                  >
                    {line || ' '}
                  </code>
                </div>
              ))}
            </pre>
          </div>

          {/* Execution Parameters */}
          <div
            className="rounded-lg overflow-hidden mt-4 shrink-0"
            style={{
              background: 'var(--color-bg-1)',
              border: '1px solid var(--color-border-1)',
            }}
          >
            <div
              className="px-4 py-3 flex items-center gap-2"
              style={{ borderBottom: '1px solid var(--color-border-1)' }}
            >
              <ProfileOutlined style={{ color: 'var(--color-primary)' }} />
              <span className="font-medium" style={{ color: 'var(--color-text-1)' }}>
                {t('job.executeParams')}
              </span>
            </div>
            <div className="p-4">
              {executeParamsText ? (
                <pre
                  className="m-0 whitespace-pre-wrap break-all font-mono text-sm overflow-auto"
                  style={{ color: 'var(--color-text-1)', maxHeight: '20vh' }}
                >
                  {executeParamsText}
                </pre>
              ) : (
                <span className="text-sm" style={{ color: 'var(--color-text-3)' }}>
                  {t('job.noExecuteParams')}
                </span>
              )}
            </div>
          </div>
        </Drawer>

        <Drawer
          open={playbookDrawerOpen}
          onClose={() => {
            setPlaybookDrawerOpen(false);
            setViewingPlaybook(null);
            setFilePreviewModalOpen(false);
            setFilePreviewData(null);
            setFilePreviewError(null);
          }}
          placement="right"
          width={600}
          title={
            viewingPlaybook ? (
              <div className="flex items-center gap-3">
                <span>{viewingPlaybook.name}</span>
                <Tag color="blue">{viewingPlaybook.version || 'v1.0.0'}</Tag>
              </div>
            ) : null
          }
          loading={playbookDetailLoading}
          styles={{
            body: {
              padding: '0 24px 24px',
            },
          }}
        >
          {viewingPlaybook && (
            <Tabs
              items={playbookViewTabs}
              className="h-full [&_.ant-tabs-content]:h-full [&_.ant-tabs-tabpane]:h-full [&_.ant-tabs-tabpane]:overflow-auto"
            />
          )}
        </Drawer>

        <Modal
          title={filePreviewData ? `${t('job.preview')}: ${filePreviewData.file_name}` : t('job.preview')}
          open={filePreviewModalOpen}
          onCancel={() => {
            setFilePreviewModalOpen(false);
            setFilePreviewData(null);
            setFilePreviewError(null);
          }}
          footer={null}
          width={800}
          styles={{ body: { maxHeight: '70vh', overflow: 'auto' } }}
        >
          {filePreviewLoading ? (
            <div className="flex items-center justify-center py-12">
              <Spin tip={t('job.loading')} />
            </div>
          ) : filePreviewError ? (
            <Alert
              message={t('job.filePreviewFailed')}
              description={filePreviewError}
              type="error"
              showIcon
            />
          ) : filePreviewData ? (
            <div>
              <div className="mb-2 text-xs" style={{ color: 'var(--color-text-3)' }}>
                {filePreviewData.file_path} ({filePreviewData.file_size} bytes)
              </div>
              <pre
                className="overflow-auto rounded p-4 text-sm"
                style={{
                  backgroundColor: 'var(--color-bg-1)',
                  border: '1px solid var(--color-border)',
                  maxHeight: '60vh',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                <code>{filePreviewData.content}</code>
              </pre>
            </div>
          ) : null}
        </Modal>
      </div>
    );
  }

  // Render list view
  return (
    <div className="w-full h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div
        className="mb-4 rounded-lg px-6 py-4 shrink-0"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <h2
          className="text-base font-medium m-0 mb-1"
          style={{ color: 'var(--color-text-1)' }}
        >
          {t('job.jobRecord')}
        </h2>
        <p className="text-sm m-0" style={{ color: 'var(--color-text-3)' }}>
          {t('job.jobRecordDesc')}
        </p>
      </div>

      {/* Table Section */}
      <div
        className="rounded-lg px-6 py-6 flex-1 min-h-0 flex flex-col"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        {/* Toolbar */}
        <div className="mb-4 flex items-center justify-between shrink-0">
          <SearchCombination
            fieldConfigs={fieldConfigs}
            onChange={handleSearchChange}
            fieldWidth={120}
            selectWidth={300}
          />
          <div className="flex items-center gap-3">
            {timeRange === 'custom' && (
              <RangePicker
                value={customRange}
                onChange={(value) => {
                  setCustomRange(value ? [value[0] as Dayjs, value[1] as Dayjs] : null);
                }}
                allowClear
              />
            )}
            <Segmented
              className="w-fit"
              options={[
                { label: t('job.today'), value: 'today' },
                { label: t('job.last7Days'), value: '7days' },
                { label: t('job.last30Days'), value: '30days' },
                { label: t('common.timeSelector.custom'), value: 'custom' },
              ]}
              value={timeRange}
              onChange={(value) => setTimeRange(value as 'today' | '7days' | '30days' | 'custom')}
            />
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 min-h-0">
          <CustomTable
            columns={columns}
            dataSource={data}
            loading={loading}
            rowKey="id"
            pagination={pagination}
            onChange={handleTableChange}
          />
        </div>
      </div>
    </div>
  );
};

export default JobRecordPage;
