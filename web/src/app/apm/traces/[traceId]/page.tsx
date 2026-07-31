'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { Alert, Col, Descriptions, Row, Space, Table, Tag, Typography } from 'antd';
import type { TableProps } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmSpanDetail, ApmTraceDetail } from '@/app/apm/types';
import { HandledRequestError } from '@/utils/request';
import SummaryMetricCard from '@/components/summary-metric-card';

type PageState = CatalogStateKind | 'ready' | 'not-found';

function spanDepth(span: ApmSpanDetail, byId: Map<string, ApmSpanDetail>, seen = new Set<string>()): number {
  if (!span.parent_span_id || seen.has(span.span_id)) return 0;
  const parent = byId.get(span.parent_span_id);
  if (!parent) return 0;
  seen.add(span.span_id);
  return 1 + spanDepth(parent, byId, seen);
}

export default function ApmTraceDetailPage() {
  const params = useParams<{ traceId: string }>();
  const { getTrace, isLoading: authLoading } = useApmApi();
  const [trace, setTrace] = useState<ApmTraceDetail>();
  const [selectedSpanId, setSelectedSpanId] = useState<string>();
  const [state, setState] = useState<PageState>('loading');

  useEffect(() => {
    if (authLoading || !params.traceId) return;
    getTrace(params.traceId)
      .then((value) => {
        setTrace(value);
        setSelectedSpanId(value.spans.find((span) => span.status === 'error')?.span_id ?? value.spans[0]?.span_id);
        setState(value.spans.length ? 'ready' : 'empty');
      })
      .catch((error) => {
        if (error instanceof HandledRequestError && error.status === 404) setState('not-found');
        else setState(catalogErrorKind(error));
      });
  }, [authLoading, getTrace, params.traceId]);

  const layout = useMemo(() => {
    if (!trace?.spans.length) return [];
    const byId = new Map(trace.spans.map((span) => [span.span_id, span]));
    const traceStart = Math.min(...trace.spans.map((span) => new Date(span.started_at).getTime()));
    const traceEnd = Math.max(...trace.spans.map((span) => new Date(span.started_at).getTime() + span.duration_ms));
    const total = Math.max(1, traceEnd - traceStart);
    return trace.spans.map((span) => ({
      span,
      depth: spanDepth(span, byId),
      left: ((new Date(span.started_at).getTime() - traceStart) / total) * 100,
      width: Math.max(0.5, (span.duration_ms / total) * 100),
    }));
  }, [trace]);

  const selected = trace?.spans.find((span) => span.span_id === selectedSpanId);
  const totalDuration = trace?.spans.length
    ? Math.max(...trace.spans.map((span) => new Date(span.started_at).getTime() + span.duration_ms))
      - Math.min(...trace.spans.map((span) => new Date(span.started_at).getTime()))
    : 0;
  const attributeRows = selected
    ? Object.entries(selected.attributes).map(([key, value]) => ({ key, value: typeof value === 'string' ? value : JSON.stringify(value) }))
    : [];
  const attributeColumns: TableProps<{ key: string; value: string }>['columns'] = [
    { title: '属性', dataIndex: 'key', width: '40%', render: (value) => <Typography.Text code>{value}</Typography.Text> },
    { title: '值', dataIndex: 'value', render: (value) => <Typography.Text className="break-all">{value}</Typography.Text> },
  ];

  return (
    <ApmRouteShell
      title="Trace 详情"
      description="查看 Span 瀑布、服务身份和经过服务端脱敏、截断的属性。"
      dependency="telemetry"
    >
      {state === 'not-found' ? (
        <ApmSurface padding="none"><CatalogState kind="empty" description="Trace 不存在、已超过保留期或当前组织无权访问。" /></ApmSurface>
      ) : state !== 'ready' ? (
        <ApmSurface padding="none"><CatalogState kind={state} /></ApmSurface>
      ) : trace ? (
        <div className="flex w-full flex-col gap-4">
          {trace.truncated ? <Alert type="warning" showIcon message="Trace 响应已达到安全上限，当前展示部分 Span 或属性。" /> : null}
          <ApmSurface padding="compact">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0">
                <Typography.Text type="secondary" className="block text-xs">Trace ID</Typography.Text>
                <Typography.Text copyable className="block truncate font-mono text-sm font-medium">
                  {trace.trace_id}
                </Typography.Text>
              </div>
              <Space wrap>
                <Tag bordered={false}>{trace.service_namespace || '未归类应用'}</Tag>
                <Tag bordered={false} color="blue">{trace.service_name}</Tag>
                <Tag bordered={false}>{trace.environment || '未设置环境'}</Tag>
              </Space>
            </div>
          </ApmSurface>
          <Row gutter={[16, 16]}>
            <Col xs={12} md={6}>
              <SummaryMetricCard layout="vertical" label="Span 数" value={trace.spans.length} className="h-full bg-[var(--color-bg)] p-4" />
            </Col>
            <Col xs={12} md={6}>
              <SummaryMetricCard
                layout="vertical"
                label="错误 Span"
                value={trace.spans.filter((span) => span.status === 'error').length}
                valueColor={trace.spans.some((span) => span.status === 'error') ? 'var(--color-fail)' : 'var(--color-text-1)'}
                className="h-full bg-[var(--color-bg)] p-4"
              />
            </Col>
            <Col xs={12} md={6}>
              <SummaryMetricCard layout="vertical" label="服务数" value={new Set(trace.spans.map((span) => span.service_name)).size} className="h-full bg-[var(--color-bg)] p-4" />
            </Col>
            <Col xs={12} md={6}>
              <SummaryMetricCard layout="vertical" label="总耗时" value={totalDuration.toFixed(2)} unit="ms" className="h-full bg-[var(--color-bg)] p-4" />
            </Col>
          </Row>
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={16}>
              <ApmSurface className="h-full">
                <div className="mb-3 flex items-center justify-between">
                  <Typography.Text strong>Span 瀑布</Typography.Text>
                  <Typography.Text type="secondary" className="text-xs tabular-nums">
                    {trace.spans.length} spans
                  </Typography.Text>
                </div>
                <div className="space-y-1 overflow-x-auto">
                  {layout.map(({ span, depth, left, width }) => (
                    <button
                      type="button"
                      key={span.span_id}
                      onClick={() => setSelectedSpanId(span.span_id)}
                      aria-pressed={selectedSpanId === span.span_id}
                      className={`flex min-h-9 w-full items-center rounded-md border-0 px-2 py-1 text-left transition-colors duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)] ${selectedSpanId === span.span_id ? 'bg-[var(--color-primary-bg-active)]' : 'bg-transparent hover:bg-[var(--color-fill-1)]'}`}
                    >
                      <div className="w-64 shrink-0 truncate text-xs" style={{ paddingLeft: depth * 12 }}>
                        <Tag bordered={false} color={span.status === 'error' ? 'error' : 'blue'}>{span.kind.toUpperCase()}</Tag>
                        {span.service_name} · {span.name}
                      </div>
                      <div className="relative h-5 min-w-[420px] flex-1 rounded bg-[var(--color-fill-1)]">
                        <div
                          className="absolute top-1 h-3 rounded-sm"
                          style={{
                            left: `${left}%`,
                            width: `${width}%`,
                            background: span.status === 'error' ? 'var(--color-fail)' : 'var(--color-primary)',
                          }}
                        />
                      </div>
                      <div className="w-24 text-right text-xs tabular-nums">{span.duration_ms.toFixed(2)} ms</div>
                    </button>
                  ))}
                </div>
              </ApmSurface>
            </Col>
            <Col xs={24} xl={8}>
              <ApmSurface className="h-full">
                <Typography.Text strong className="mb-3 block">Span 详情</Typography.Text>
                {selected ? (
                  <Space direction="vertical" className="w-full">
                    <Descriptions size="small" column={1}>
                      <Descriptions.Item label="操作">{selected.name}</Descriptions.Item>
                      <Descriptions.Item label="服务">{selected.service_namespace || '未归类应用'} / {selected.service_name}</Descriptions.Item>
                      <Descriptions.Item label="实例">{selected.instance_id || '身份缺失'}</Descriptions.Item>
                      <Descriptions.Item label="Span ID"><Typography.Text copyable>{selected.span_id}</Typography.Text></Descriptions.Item>
                    </Descriptions>
                    <Table rowKey="key" size="small" columns={attributeColumns} dataSource={attributeRows} pagination={false} />
                  </Space>
                ) : null}
              </ApmSurface>
            </Col>
          </Row>
        </div>
      ) : null}
    </ApmRouteShell>
  );
}
