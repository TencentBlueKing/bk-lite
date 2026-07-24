'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Space, Card, Button, message, Tag, Popconfirm, Spin } from 'antd';
import PermissionWrapper from '@/components/permission';
import CustomTable from '@/components/custom-table';
import {
  ArrowRightOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  FileTextOutlined,
  DesktopOutlined,
  CheckCircleOutlined,
  EyeOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
  ToolOutlined,
  AlertOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import usePatchManagerApi from '@/app/patch-manager/api';
import { PatchDashboardStats, ComplianceDistributionItem, RecentTaskItem, TopRiskItem } from '@/app/patch-manager/types';

interface KpiProps {
  label: string;
  value: string | number;
  color?: string;
  arrow?: boolean;
  icon?: React.ReactNode;
  onClick?: () => void;
}

function Kpi({ label, value, color, arrow, icon, onClick }: KpiProps) {
  return (
    <div
      onClick={onClick}
      style={{
        background: 'var(--color-bg-1, #fff)',
        border: '1px solid var(--color-border-1, #e8e8e8)',
        borderRadius: 10,
        padding: '14px 16px',
        minWidth: 130,
        flex: 1,
        cursor: onClick ? 'pointer' : 'default',
        transition: 'box-shadow 0.2s',
      }}
      onMouseEnter={(e) => {
        if (onClick) e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.06)';
      }}
      onMouseLeave={(e) => {
        if (onClick) e.currentTarget.style.boxShadow = 'none';
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <div style={{ fontSize: 13, color: 'var(--color-text-2, #595959)', display: 'flex', alignItems: 'center', gap: 4 }}>
          {label}{arrow && <ArrowRightOutlined style={{ fontSize: 12 }} />}
        </div>
        {icon && <span style={{ color: color || 'var(--color-primary, #1677ff)', fontSize: 18 }}>{icon}</span>}
      </div>
      <div style={{ fontSize: 26, fontWeight: 500, color: color || 'var(--color-text-1, #1f1f1f)' }}>{value}</div>
    </div>
  );
}

export default function HomePage() {
  const api = usePatchManagerApi();
  const { isLoading } = useApiClient();
  const router = useRouter();
  const [stats, setStats] = useState<PatchDashboardStats | null>(null);
  const [assessLoading, setAssessLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [tableHeight, setTableHeight] = useState(300);

  useEffect(() => {
    const updateHeight = () => {
      if (!bottomRef.current) return;
      const rect = bottomRef.current.getBoundingClientRect();
      const height = window.innerHeight - rect.top - 24;
      setTableHeight(Math.max(160, height));
    };
    updateHeight();
    window.addEventListener('resize', updateHeight);
    return () => window.removeEventListener('resize', updateHeight);
  }, [stats]);

  useEffect(() => {
    if (isLoading) return;
    const loadStats = async () => {
      try {
        const data = await api.getPatchDashboardStats();
        setStats(data);
      } catch {
      } finally {
        setPageLoading(false);
      }
    };
    loadStats();
  }, [isLoading]);

  const handleImmediateAssess = async () => {
    setAssessLoading(true);
    try {
      const res = await api.getPatchTargetList({ page: 1, page_size: -1 });
      const targets = Array.isArray(res) ? res : (res.items || []);
      if (targets.length === 0) {
        message.info('当前没有纳管主机');
        return;
      }
      await api.createGovernanceTask({
        task_type: 'assess',
        target_list: targets.map((t: any) => t.id),
        execution_mode: 'now',
      });
      message.success(`已创建全局评估任务，包含 ${targets.length} 台主机`);
    } catch {
    } finally {
      setAssessLoading(false);
    }
  };

  const kpis = [
    { label: '纳管主机', value: stats?.target_total ?? '—', icon: <DesktopOutlined /> },
    { label: '已评估合规率', value: stats?.compliance_rate != null ? `${stats.compliance_rate}%` : '—', color: '#0F6E56', icon: <CheckCircleOutlined /> },
    { label: '评估覆盖率', value: stats?.coverage_rate != null ? `${stats.coverage_rate}%` : '—', icon: <EyeOutlined /> },
    { label: '不合规主机', value: stats?.non_compliant_hosts ?? '—', color: '#A32D2D', icon: <WarningOutlined /> },
    { label: '未配置基线', value: stats?.unconfigured_hosts ?? '—', color: '#854F0B', icon: <ExclamationCircleOutlined /> },
    { label: '待治理风险', value: stats?.pending_risk_count ?? '—', color: '#854F0B', icon: <ToolOutlined /> },
    { label: '修复异常', value: stats?.failed_tasks ?? '—', color: '#A32D2D', icon: <AlertOutlined /> },
  ];

  const dist: ComplianceDistributionItem[] = stats?.compliance_distribution || [];
  const distTotal = dist.reduce((sum: number, d) => sum + (d.count || 0), 0) || 1;
  const compliantCount = dist.find((d) => d.filter === 'compliant')?.count || 0;
  const nonCompliantCount = dist.find((d) => d.filter === 'non_compliant')?.count || 0;
  const failedCount = dist.find((d) => d.filter === 'failed')?.count || 0;
  const denom = compliantCount + nonCompliantCount;
  const rateHint = denom > 0 ? ` = ${compliantCount} / ${denom} ≈ ${Math.round(compliantCount / denom * 100)}%` : '';
  const assessedCount = compliantCount + nonCompliantCount + failedCount;
  const targetTotal = stats?.target_total ?? 0;
  const coverageHint = targetTotal > 0 ? ` = ${assessedCount} / ${targetTotal} ≈ ${Math.round(assessedCount / targetTotal * 100)}%` : '';

  const FILTER_COLORS: Record<string, string> = {
    compliant: '#1D9E75',
    non_compliant: '#E24B4A',
    pending: '#A4A19E',
    failed: '#6B7280',
    unconfigured: '#EF9F27',
  };

  const distributionOption = useMemo(() => ({
    grid: { left: 0, right: 0, top: 0, bottom: 0, height: 16 },
    tooltip: { trigger: 'item' },
    xAxis: {
      type: 'value',
      show: false,
      min: 0,
      max: distTotal,
    },
    yAxis: {
      type: 'category',
      show: false,
      data: [''],
    },
    series: dist.map((d) => ({
      name: d.label,
      type: 'bar',
      stack: 'total',
      barWidth: 16,
      itemStyle: { color: FILTER_COLORS[d.filter || ''] || '#A4A19E', borderRadius: 0 },
      data: [d.count],
      emphasis: { focus: 'series' },
    })),
  }), [dist, distTotal]);

  return (
    <div style={{ position: 'relative', overflowX: 'hidden' }}>
      {pageLoading && (
        <div style={{
          position: 'absolute',
          top: 0, left: 0, right: 0, bottom: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'rgba(255, 255, 255, 0.5)',
          zIndex: 10,
        }}>
          <Spin />
        </div>
      )}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
        {kpis.map((kpi) => (
          <Kpi key={kpi.label} label={kpi.label} value={kpi.value} color={kpi.color} icon={kpi.icon} />
        ))}
      </div>
      {/* 第2行：主机合规分布 */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ background: 'var(--color-bg-1, #fff)', border: '1px solid var(--color-border-1, #e8e8e8)', borderRadius: 10, padding: '12px 16px', flex: '1 1 100%', minWidth: 0, maxWidth: '100%', minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontWeight: 500, marginBottom: 10 }}>主机合规分布</div>
          <div style={{ height: 16, borderRadius: 8, overflow: 'hidden' }}>
            <ReactECharts
              option={distributionOption}
              style={{ height: '100%', width: '100%' }}
              opts={{ renderer: 'svg' }}
            />
          </div>
          <Space size={16} wrap style={{ marginTop: 10 }}>
            {dist.map((d) => (
              <span key={d.label} style={{ fontSize: 12, color: 'var(--color-text-2, #595959)' }}>
                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: FILTER_COLORS[d.filter || ''] || '#A4A19E', marginRight: 5 }} />{d.label} {d.count}
              </span>
            ))}
          </Space>
          <div style={{ marginTop: 10, fontSize: 12, color: 'var(--color-text-3, #8c8c8c)' }}>
            合规率 = 合规 / (合规+不合规){rateHint}；评估覆盖率 = 已评估 / 纳管主机{coverageHint}；未配置/待评估/评估失败不计入合规率；分母为 0 时显示 -。
          </div>
        </div>
      </div>

      {/* 快捷操作 */}
      <Card
        title={<span><PlayCircleOutlined style={{ marginRight: 6 }} />快捷操作</span>}
        style={{ borderRadius: 10, marginBottom: 14 }}
        styles={{ body: { padding: '12px 16px' } }}
      >
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Card size="small" style={{ flex: '1 1 200px', borderRadius: 8 }} styles={{ body: { padding: 14 } }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'var(--color-fill-2, #f0f2f5)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-primary, #1677ff)' }}><PlayCircleOutlined /></div>
              <div style={{ fontWeight: 500 }}>立即评估</div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-text-3, #8c8c8c)', marginBottom: 12, minHeight: 34 }}>立即对所有主机执行一次合规评估，刷新风险数据。</div>
            <PermissionWrapper
              requiredPermissions={['Add']}
              permissionPath="/patch-manager/risk-execution"
              className="block!"
            >
              <Popconfirm title="确定对所有主机执行合规评估？" onConfirm={handleImmediateAssess} okText="确定" cancelText="取消">
                <Button type="primary" block icon={<PlayCircleOutlined />} loading={assessLoading}>立即评估</Button>
              </Popconfirm>
            </PermissionWrapper>
          </Card>
          <Card size="small" style={{ flex: '1 1 200px', borderRadius: 8 }} styles={{ body: { padding: 14 } }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'var(--color-fill-2, #f0f2f5)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-primary, #1677ff)' }}><PlusOutlined /></div>
              <div style={{ fontWeight: 500 }}>添加主机</div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-text-3, #8c8c8c)', marginBottom: 12, minHeight: 34 }}>将新的 Windows 或 Linux 主机纳入补丁管理。</div>
            <Button type="primary" block icon={<PlusOutlined />} onClick={() => router.push('/patch-manager/target')}>添加主机</Button>
          </Card>
          <Card size="small" style={{ flex: '1 1 200px', borderRadius: 8 }} styles={{ body: { padding: 14 } }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'var(--color-fill-2, #f0f2f5)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-primary, #1677ff)' }}><PlusOutlined /></div>
              <div style={{ fontWeight: 500 }}>新建基线</div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-text-3, #8c8c8c)', marginBottom: 12, minHeight: 34 }}>定义主机应满足的补丁/包版本要求。</div>
            <Button type="primary" block icon={<PlusOutlined />} onClick={() => router.push('/patch-manager/baseline')}>新建基线</Button>
          </Card>
          <Card size="small" style={{ flex: '1 1 200px', borderRadius: 8 }} styles={{ body: { padding: 14 } }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'var(--color-fill-2, #f0f2f5)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-primary, #1677ff)' }}><FileTextOutlined /></div>
              <div style={{ fontWeight: 500 }}>执行记录</div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-text-3, #8c8c8c)', marginBottom: 12, minHeight: 34 }}>查看治理任务的执行进度、结果和日志。</div>
            <Button type="primary" block icon={<FileTextOutlined />} onClick={() => router.push('/patch-manager/risk-execution')}>查看记录</Button>
          </Card>
        </div>
      </Card>

      {/* 第3行：最近执行 + TOP风险 */}
      <div ref={bottomRef} style={{ display: 'flex', gap: 14, flexWrap: 'nowrap', height: tableHeight }}>
        <Card
          title={<span><FileTextOutlined style={{ marginRight: 6 }} />最近执行记录</span>}
          style={{ flex: '2 1 0', minWidth: 0, borderRadius: 10, height: '100%', display: 'flex', flexDirection: 'column' }}
          styles={{ body: { padding: '10px 10px', flex: 1, overflow: 'hidden' } }}
          extra={<Button type="link" size="small" onClick={() => router.push('/patch-manager/risk-execution')}>查看更多</Button>}
        >
          <CustomTable<RecentTaskItem>
            size="small"
            pagination={false}
            rowKey="id"
            dataSource={stats?.recent_tasks || []}
            scroll={{ y: Math.max(120, tableHeight - 76) }}
            columns={[
              { title: '任务名称', dataIndex: 'name', ellipsis: true },
              { title: '状态', dataIndex: 'status', width: 100, render: (_: unknown, r: RecentTaskItem) => <Tag color={r.status_color}>{r.status}</Tag> },
              { title: '进度', dataIndex: 'progress', width: 80 },
              { title: '时间', dataIndex: 'time', width: 100, render: (v: string) => <span style={{ color: 'var(--color-text-3, #8c8c8c)' }}>{v}</span> },
            ]}
          />
        </Card>

        <Card
          title={<span><ArrowRightOutlined style={{ marginRight: 6 }} />TOP 风险补丁</span>}
          style={{ flex: '1 1 0', minWidth: 0, borderRadius: 10, height: '100%', display: 'flex', flexDirection: 'column' }}
          styles={{ body: { padding: '10px 10px', flex: 1, overflow: 'hidden' } }}
          extra={<Button type="link" size="small" onClick={() => router.push('/patch-manager/risk-pending')}>查看全部</Button>}
        >
          <CustomTable<TopRiskItem>
            size="small"
            pagination={false}
            rowKey="id"
            dataSource={stats?.top_risks || []}
            scroll={{ y: Math.max(120, tableHeight - 76) }}
            columns={[
              { title: '补丁要求', dataIndex: 'patch', ellipsis: true },
              { title: '影响主机', dataIndex: 'hosts', width: 90, render: (v: number) => `${v} 台` },
              { title: '严重级别', dataIndex: 'sev', width: 90, render: (v: string) => <Tag color={v === '严重' ? 'error' : 'warning'}>{v}</Tag> },
            ]}
          />
        </Card>
      </div>
    </div>
  );
}
