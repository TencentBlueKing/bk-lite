'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  Button,
  Drawer,
  Empty,
  Flex,
  Popconfirm,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useConfigFileApi } from '@/app/cmdb/api';
import type {
  ConfigFileContentResponse,
  ConfigFileItem,
  ConfigFileVersion,
} from '@/app/cmdb/types/configFile';

const { Paragraph, Text } = Typography;

const ENCODING_OPTIONS = [
  { label: 'UTF-8', value: 'utf-8' },
  { label: 'GBK', value: 'gbk' },
  { label: 'GB18030', value: 'gb18030' },
  { label: 'Big5', value: 'big5' },
  { label: 'Shift_JIS', value: 'shift_jis' },
  { label: 'UTF-16LE', value: 'utf-16le' },
];

const formatDateTime = (value: string) => {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
};

interface DiffRow {
  key: string;
  leftNumber: number | null;
  rightNumber: number | null;
  leftText: string;
  rightText: string;
  status: 'same' | 'changed' | 'added' | 'removed';
}

interface DiffSegment {
  text: string;
  changed: boolean;
}

const buildSideBySideDiffRows = (leftContent: string, rightContent: string): DiffRow[] => {
  const leftLines = leftContent.split(/\r?\n/);
  const rightLines = rightContent.split(/\r?\n/);
  const leftLength = leftLines.length;
  const rightLength = rightLines.length;
  const dp = Array.from({ length: leftLength + 1 }, () => Array(rightLength + 1).fill(0));

  for (let leftIndex = leftLength - 1; leftIndex >= 0; leftIndex -= 1) {
    for (let rightIndex = rightLength - 1; rightIndex >= 0; rightIndex -= 1) {
      if (leftLines[leftIndex] === rightLines[rightIndex]) {
        dp[leftIndex][rightIndex] = dp[leftIndex + 1][rightIndex + 1] + 1;
      } else {
        dp[leftIndex][rightIndex] = Math.max(dp[leftIndex + 1][rightIndex], dp[leftIndex][rightIndex + 1]);
      }
    }
  }

  const rows: DiffRow[] = [];
  let leftIndex = 0;
  let rightIndex = 0;
  let leftNumber = 1;
  let rightNumber = 1;

  while (leftIndex < leftLength && rightIndex < rightLength) {
    if (leftLines[leftIndex] === rightLines[rightIndex]) {
      rows.push({
        key: `${leftIndex}-${rightIndex}`,
        leftNumber,
        rightNumber,
        leftText: leftLines[leftIndex],
        rightText: rightLines[rightIndex],
        status: 'same',
      });
      leftIndex += 1;
      rightIndex += 1;
      leftNumber += 1;
      rightNumber += 1;
      continue;
    }

    if (dp[leftIndex + 1][rightIndex] === dp[leftIndex][rightIndex + 1]) {
      rows.push({
        key: `${leftIndex}-${rightIndex}`,
        leftNumber,
        rightNumber,
        leftText: leftLines[leftIndex],
        rightText: rightLines[rightIndex],
        status: 'changed',
      });
      leftIndex += 1;
      rightIndex += 1;
      leftNumber += 1;
      rightNumber += 1;
      continue;
    }

    if (dp[leftIndex + 1][rightIndex] > dp[leftIndex][rightIndex + 1]) {
      rows.push({
        key: `${leftIndex}-left`,
        leftNumber,
        rightNumber: null,
        leftText: leftLines[leftIndex],
        rightText: '',
        status: 'removed',
      });
      leftIndex += 1;
      leftNumber += 1;
      continue;
    }

    rows.push({
      key: `${rightIndex}-right`,
      leftNumber: null,
      rightNumber,
      leftText: '',
      rightText: rightLines[rightIndex],
      status: 'added',
    });
    rightIndex += 1;
    rightNumber += 1;
  }

  while (leftIndex < leftLength) {
    rows.push({
      key: `${leftIndex}-left-tail`,
      leftNumber,
      rightNumber: null,
      leftText: leftLines[leftIndex],
      rightText: '',
      status: 'removed',
    });
    leftIndex += 1;
    leftNumber += 1;
  }

  while (rightIndex < rightLength) {
    rows.push({
      key: `${rightIndex}-right-tail`,
      leftNumber: null,
      rightNumber,
      leftText: '',
      rightText: rightLines[rightIndex],
      status: 'added',
    });
    rightIndex += 1;
    rightNumber += 1;
  }

  return rows;
};

const getDiffAccentClassName = (status: DiffRow['status'], side: 'left' | 'right') => {
  if (status === 'changed') return 'border-l-2 border-l-amber-400';
  if (status === 'added' && side === 'right') return 'border-l-2 border-l-emerald-400';
  if (status === 'removed' && side === 'left') return 'border-l-2 border-l-rose-400';
  return 'border-l-2 border-l-transparent';
};

const buildInlineSegments = (leftText: string, rightText: string) => {
  if (leftText === rightText) {
    return {
      left: [{ text: leftText, changed: false }],
      right: [{ text: rightText, changed: false }],
    };
  }

  let prefixLength = 0;
  const maxPrefixLength = Math.min(leftText.length, rightText.length);
  while (prefixLength < maxPrefixLength && leftText[prefixLength] === rightText[prefixLength]) {
    prefixLength += 1;
  }

  let leftSuffixLength = leftText.length - 1;
  let rightSuffixLength = rightText.length - 1;
  while (
    leftSuffixLength >= prefixLength &&
    rightSuffixLength >= prefixLength &&
    leftText[leftSuffixLength] === rightText[rightSuffixLength]
  ) {
    leftSuffixLength -= 1;
    rightSuffixLength -= 1;
  }

  const buildSegments = (source: string, suffixIndex: number): DiffSegment[] => {
    const segments: DiffSegment[] = [];
    const prefix = source.slice(0, prefixLength);
    const changed = source.slice(prefixLength, suffixIndex + 1);
    const suffix = source.slice(suffixIndex + 1);

    if (prefix) segments.push({ text: prefix, changed: false });
    if (changed) segments.push({ text: changed, changed: true });
    if (suffix) segments.push({ text: suffix, changed: false });
    if (!segments.length) segments.push({ text: '', changed: false });
    return segments;
  };

  return {
    left: buildSegments(leftText, leftSuffixLength),
    right: buildSegments(rightText, rightSuffixLength),
  };
};

const ConfigFilesPage = () => {
  const searchParams = useSearchParams();
  const instanceId = searchParams.get('inst_id') || '';
  const configFileApi = useConfigFileApi();
  const {
    getConfigFileList,
    getConfigFileVersions,
    getConfigFileContent,
    deleteConfigFileVersion,
  } = configFileApi;
  const [fileList, setFileList] = useState<ConfigFileItem[]>([]);
  const [fileListLoading, setFileListLoading] = useState(false);
  const [contentDrawerOpen, setContentDrawerOpen] = useState(false);
  const [activeFile, setActiveFile] = useState<ConfigFileItem | null>(null);
  const [contentData, setContentData] = useState<ConfigFileContentResponse | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentEncoding, setContentEncoding] = useState('utf-8');
  const [compareDrawerOpen, setCompareDrawerOpen] = useState(false);
  const [compareTarget, setCompareTarget] = useState<ConfigFileItem | null>(null);
  const [versionList, setVersionList] = useState<ConfigFileVersion[]>([]);
  const [versionListLoading, setVersionListLoading] = useState(false);
  const [leftCompareVersionId, setLeftCompareVersionId] = useState<number | undefined>();
  const [rightCompareVersionId, setRightCompareVersionId] = useState<number | undefined>();
  const [leftCompareContent, setLeftCompareContent] = useState('');
  const [rightCompareContent, setRightCompareContent] = useState('');
  const [compareLoading, setCompareLoading] = useState(false);
  const leftPaneRef = useRef<HTMLDivElement | null>(null);
  const rightPaneRef = useRef<HTMLDivElement | null>(null);
  const syncingScrollRef = useRef(false);

  const fetchFileList = async () => {
    if (!instanceId) {
      setFileList([]);
      return;
    }
    try {
      setFileListLoading(true);
      const data = await getConfigFileList(instanceId);
      setFileList(Array.isArray(data) ? data : []);
    } finally {
      setFileListLoading(false);
    }
  };

  useEffect(() => {
    void fetchFileList();
  }, [getConfigFileList, instanceId]);

  const fetchContent = async (record: ConfigFileItem, encoding = 'utf-8') => {
    try {
      setContentLoading(true);
      const data = await getConfigFileContent(record.latest_version_id, encoding);
      setActiveFile(record);
      setContentData(data || null);
      setContentEncoding(data?.encoding || encoding);
      setContentDrawerOpen(true);
    } finally {
      setContentLoading(false);
    }
  };

  const handleEncodingChange = async (encoding: string) => {
    if (!activeFile) return;
    setContentEncoding(encoding);
    await fetchContent(activeFile, encoding);
  };

  const handleCopyContent = async () => {
    try {
      await navigator.clipboard.writeText(contentData?.content || '');
      message.success('文件内容已复制');
    } catch {
      message.error('复制失败');
    }
  };

  const openCompareDrawer = async (record: ConfigFileItem) => {
    try {
      setVersionListLoading(true);
      const data = await getConfigFileVersions(instanceId, record.file_path);
      const items = Array.isArray(data) ? data : data?.items || [];
      if (items.length < 2) {
        message.warning('当前文件只有一个版本，无法进行版本对比');
        return;
      }
      setCompareTarget(record);
      setVersionList(items);
      setLeftCompareVersionId(items[0]?.id);
      setRightCompareVersionId(items[1]?.id);
      setLeftCompareContent('');
      setRightCompareContent('');
      setCompareDrawerOpen(true);
    } finally {
      setVersionListLoading(false);
    }
  };

  const handleDelete = async (record: ConfigFileItem) => {
    await deleteConfigFileVersion(record.latest_version_id);
    message.success('删除成功');
    if (activeFile?.latest_version_id === record.latest_version_id) {
      setContentDrawerOpen(false);
      setActiveFile(null);
      setContentData(null);
    }
    await fetchFileList();
  };

  useEffect(() => {
    if (!compareDrawerOpen || !leftCompareVersionId) {
      setLeftCompareContent('');
      setRightCompareContent('');
      return;
    }

    let mounted = true;
    const fetchCompareContent = async () => {
      try {
        setCompareLoading(true);
        const leftData = await getConfigFileContent(leftCompareVersionId, 'utf-8');
        const rightData = rightCompareVersionId
          ? await getConfigFileContent(rightCompareVersionId, 'utf-8')
          : null;
        if (!mounted) return;
        setLeftCompareContent(leftData?.content || '');
        setRightCompareContent(rightData?.content || '');
      } finally {
        if (mounted) {
          setCompareLoading(false);
        }
      }
    };

    void fetchCompareContent();
    return () => {
      mounted = false;
    };
  }, [compareDrawerOpen, getConfigFileContent, leftCompareVersionId, rightCompareVersionId]);

  const syncScroll = (source: 'left' | 'right') => {
    const sourcePane = source === 'left' ? leftPaneRef.current : rightPaneRef.current;
    const targetPane = source === 'left' ? rightPaneRef.current : leftPaneRef.current;
    if (!sourcePane || !targetPane || syncingScrollRef.current) return;

    syncingScrollRef.current = true;
    targetPane.scrollTop = sourcePane.scrollTop;
    targetPane.scrollLeft = sourcePane.scrollLeft;
    requestAnimationFrame(() => {
      syncingScrollRef.current = false;
    });
  };

  const versionOptions = useMemo(
    () => versionList.map((item) => ({
      label: `${item.version} | ${formatDateTime(item.created_at)}`,
      value: item.id,
    })),
    [versionList]
  );

  const leftVersion = useMemo(
    () => versionList.find((item) => item.id === leftCompareVersionId),
    [leftCompareVersionId, versionList]
  );

  const rightVersion = useMemo(
    () => versionList.find((item) => item.id === rightCompareVersionId),
    [rightCompareVersionId, versionList]
  );

  const diffRows = useMemo(
    () => buildSideBySideDiffRows(leftCompareContent, rightCompareContent),
    [leftCompareContent, rightCompareContent]
  );

  const diffRowsWithSegments = useMemo(
    () => diffRows.map((row) => ({
      ...row,
      segments: buildInlineSegments(row.leftText, row.rightText),
    })),
    [diffRows]
  );

  const diffSummary = useMemo(() => {
    return diffRows.reduce(
      (acc, row) => {
        if (row.status === 'changed') acc.changed += 1;
        if (row.status === 'added') acc.added += 1;
        if (row.status === 'removed') acc.removed += 1;
        return acc;
      },
      { changed: 0, added: 0, removed: 0 }
    );
  }, [diffRows]);

  const columns: ColumnsType<ConfigFileItem> = [
    {
      title: '名称',
      dataIndex: 'file_name',
      key: 'file_name',
      width: 240,
      render: (_, record) => (
        <div className="py-1">
          <div className="font-medium text-[14px] text-[var(--color-text-primary)]">{record.file_name}</div>
          <Text type="secondary">任务 #{record.collect_task_id}</Text>
        </div>
      ),
    },
    {
      title: '版本号',
      dataIndex: 'latest_version',
      key: 'latest_version',
      width: 180,
      render: (value) => (
        <Text className="font-mono text-[13px] text-[var(--color-text-primary)]">{value}</Text>
      ),
    },
    {
      title: '采集路径',
      dataIndex: 'file_path',
      key: 'file_path',
      width: 240,
      ellipsis: true,
      render: (value) => (
        <Paragraph className="mb-0 text-[13px]" ellipsis={{ rows: 2, tooltip: value }}>
          {value}
        </Paragraph>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'latest_created_at',
      key: 'latest_created_at',
      width: 200,
      render: (value) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 280,
      fixed: 'right',
      render: (_, record) => (
        <Space size={0} split={<Text type="secondary">|</Text>}>
          <Button type="link" size="small" onClick={() => void fetchContent(record)}>
            查看文件内容
          </Button>
          <Button type="link" size="small" onClick={() => void openCompareDrawer(record)}>
            版本对比
          </Button>
          <Popconfirm
            title="确认删除当前最新版本记录？"
            description="删除后该文件会回退到上一条可用版本，若无历史版本则会从列表中消失。"
            okText="删除"
            cancelText="取消"
            onConfirm={() => void handleDelete(record)}
          >
            <Button danger type="link" size="small">
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  if (!instanceId) {
    return <Empty description="缺少实例信息" />;
  }

  return (
    <>
      <div className="rounded-xl border border-[var(--color-border)] bg-white p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
        <Flex justify="space-between" align="center" className="mb-4">
          <div>
            <div className="text-[16px] font-semibold text-[var(--color-text-primary)]">配置文件列表</div>
            <Text type="secondary">按主机维度查看最新版本的配置文件记录</Text>
          </div>
        </Flex>
        <Table
          rowKey="latest_version_id"
          className="[&_.ant-table-thead_th]:!bg-[var(--color-fill-1)] [&_.ant-table-thead_th]:!py-3.5 [&_.ant-table-thead_th]:text-sm [&_.ant-table-thead_th]:font-semibold [&_.ant-table-tbody_td]:!py-4 [&_.ant-table-tbody_tr:hover_td]:!bg-[var(--color-fill-1)] [&_.ant-table-placeholder_td]:!py-10"
          loading={fileListLoading}
          dataSource={fileList}
          columns={columns}
          pagination={{
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            defaultPageSize: 10,
            showTotal: (total) => `共 ${total} 条`,
          }}
          locale={{ emptyText: <Empty description="当前实例暂无配置文件采集记录" /> }}
          scroll={{ x: 1120 }}
        />
      </div>

      <Drawer
        title={activeFile ? `文件内容 · ${activeFile.file_name}` : '文件内容'}
        placement="right"
        width={760}
        open={contentDrawerOpen}
        onClose={() => setContentDrawerOpen(false)}
        extra={
          <Space>
            <Button onClick={() => void handleCopyContent()}>复制内容</Button>
            <Text type="secondary">编码</Text>
            <Select
              value={contentEncoding}
              options={ENCODING_OPTIONS}
              style={{ width: 130 }}
              onChange={(value) => void handleEncodingChange(value)}
            />
          </Space>
        }
      >
        <Spin spinning={contentLoading}>
          <Space direction="vertical" size={12} className="w-full">
            <div className="rounded-lg bg-[var(--color-fill-1)] p-3">
              <div><Text type="secondary">配置文件名称：</Text>{activeFile?.file_name || '--'}</div>
              <div><Text type="secondary">采集路径：</Text>{activeFile?.file_path || '--'}</div>
              <div><Text type="secondary">版本号：</Text>{activeFile?.latest_version || '--'}</div>
            </div>
            <pre className="max-h-[calc(100vh-240px)] overflow-auto rounded-lg bg-[#0f172a] p-4 text-xs leading-6 text-[#e2e8f0]">
              {contentData?.content || '暂无内容'}
            </pre>
          </Space>
        </Spin>
      </Drawer>

      <Drawer
        title={compareTarget ? `版本对比 · ${compareTarget.file_name}` : '版本对比'}
        placement="right"
        width={1320}
        open={compareDrawerOpen}
        onClose={() => {
          setCompareDrawerOpen(false);
          setCompareTarget(null);
          setVersionList([]);
          setLeftCompareVersionId(undefined);
          setRightCompareVersionId(undefined);
          setLeftCompareContent('');
          setRightCompareContent('');
        }}
      >
        <div className="flex h-full flex-col gap-4">
          <div className="rounded-2xl border border-[var(--color-border)] bg-white p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
            <Flex justify="space-between" align="start" gap={16} wrap="wrap">
              <Space wrap size={12}>
                <Select
                  placeholder="选择左侧版本"
                  value={leftCompareVersionId}
                  options={versionOptions}
                  loading={versionListLoading}
                  style={{ width: 330 }}
                  onChange={setLeftCompareVersionId}
                />
                <Select
                  placeholder="选择右侧版本"
                  value={rightCompareVersionId}
                  options={versionOptions.filter((option) => option.value !== leftCompareVersionId)}
                  loading={versionListLoading}
                  style={{ width: 330 }}
                  onChange={setRightCompareVersionId}
                  allowClear
                />
              </Space>
              <Space wrap size={8}>
                <Tag color="gold">修改 {diffSummary.changed}</Tag>
                <Tag color="green">新增 {diffSummary.added}</Tag>
                <Tag color="red">删除 {diffSummary.removed}</Tag>
              </Space>
            </Flex>
          </div>

          <Spin spinning={versionListLoading || compareLoading}>
            <div className="grid h-[calc(100vh-220px)] grid-cols-2 gap-4">
              <div className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
                <div className="border-b border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-3">
                  <div className="text-xs text-[var(--color-text-secondary)]">左侧版本</div>
                  <div className="mt-1 font-mono text-[13px] text-[var(--color-text-primary)]">{leftVersion?.version || '--'}</div>
                  <div className="text-xs text-[var(--color-text-secondary)]">{leftVersion ? formatDateTime(leftVersion.created_at) : '--'}</div>
                </div>
                <div
                  ref={leftPaneRef}
                  onScroll={() => syncScroll('left')}
                  className="min-h-0 flex-1 overflow-auto bg-[#0f172a] px-0 py-3"
                >
                  {diffRowsWithSegments.length ? diffRowsWithSegments.map((row) => (
                    <div
                      key={`${row.key}-left`}
                      className="grid grid-cols-[56px_1fr] text-xs leading-6 text-[#e2e8f0]"
                    >
                      <div className="px-3 py-1 text-right font-mono text-[#64748b]">
                        {row.leftNumber ?? ''}
                      </div>
                      <pre className={`overflow-x-auto px-3 py-1 whitespace-pre-wrap break-all ${getDiffAccentClassName(row.status, 'left')}`}>
                        {row.segments.left.map((segment, index) => (
                          <span
                            key={`${row.key}-left-${index}`}
                            className={segment.changed ? 'rounded-sm bg-amber-300/20 px-0.5 text-amber-100' : ''}
                          >
                            {segment.text || (index === 0 ? ' ' : '')}
                          </span>
                        ))}
                      </pre>
                    </div>
                  )) : (
                    <div className="px-4 py-10 text-center text-sm text-[#94a3b8]">请选择两个版本进行对比</div>
                  )}
                </div>
              </div>

              <div className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
                <div className="border-b border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-3">
                  <div className="text-xs text-[var(--color-text-secondary)]">右侧版本</div>
                  <div className="mt-1 font-mono text-[13px] text-[var(--color-text-primary)]">{rightVersion?.version || '--'}</div>
                  <div className="text-xs text-[var(--color-text-secondary)]">{rightVersion ? formatDateTime(rightVersion.created_at) : '--'}</div>
                </div>
                <div
                  ref={rightPaneRef}
                  onScroll={() => syncScroll('right')}
                  className="min-h-0 flex-1 overflow-auto bg-[#0f172a] px-0 py-3"
                >
                  {diffRowsWithSegments.length ? diffRowsWithSegments.map((row) => (
                    <div
                      key={`${row.key}-right`}
                      className="grid grid-cols-[56px_1fr] text-xs leading-6 text-[#e2e8f0]"
                    >
                      <div className="px-3 py-1 text-right font-mono text-[#64748b]">
                        {row.rightNumber ?? ''}
                      </div>
                      <pre className={`overflow-x-auto px-3 py-1 whitespace-pre-wrap break-all ${getDiffAccentClassName(row.status, 'right')}`}>
                        {row.segments.right.map((segment, index) => (
                          <span
                            key={`${row.key}-right-${index}`}
                            className={segment.changed ? 'rounded-sm bg-amber-300/20 px-0.5 text-amber-100' : ''}
                          >
                            {segment.text || (index === 0 ? ' ' : '')}
                          </span>
                        ))}
                      </pre>
                    </div>
                  )) : (
                    <div className="px-4 py-10 text-center text-sm text-[#94a3b8]">请选择两个版本进行对比</div>
                  )}
                </div>
              </div>
            </div>
          </Spin>
        </div>
      </Drawer>
    </>
  );
};

export default ConfigFilesPage;
