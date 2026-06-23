'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Empty, List, Row, Spin, Statistic, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { GraphEdge, WikiGraph } from '@/app/opspilot/types/wiki';
import GraphCanvas from '@/app/opspilot/components/wiki/GraphCanvas';

const GraphTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchGraphAnalysis, rebuildRelations } = useWikiApi();
  const [graph, setGraph] = useState<WikiGraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setGraph(await fetchGraphAnalysis(kbId));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const titleOf = useMemo(() => {
    const map = new Map<number, string>();
    (graph?.nodes || []).forEach((n) => map.set(n.id, n.title));
    return (id: number) => map.get(id) || `#${id}`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph]);

  const handleRebuild = async () => {
    setRebuilding(true);
    try {
      await rebuildRelations(kbId);
      load();
    } finally {
      setRebuilding(false);
    }
  };

  if (!graph) {
    return (
      <Spin spinning={loading}>
        <Empty />
      </Spin>
    );
  }

  const insights = (graph.insights || {}) as Record<string, number>;
  const strongest = (graph.insights?.strongest_edges as GraphEdge[] | undefined) || [];

  const edgeColumns: ColumnsType<GraphEdge> = [
    { title: t('wiki.from'), key: 'from', render: (_: unknown, e) => titleOf(e.from) },
    { title: t('wiki.to'), key: 'to', render: (_: unknown, e) => titleOf(e.to) },
    { title: t('wiki.weight'), dataIndex: 'weight', key: 'weight', width: 100 },
    {
      title: t('wiki.signals'),
      key: 'signals',
      render: (_: unknown, e) => (
        <>
          {Object.keys(e.signals || {}).map((s) => (
            <Tag key={s}>{s}</Tag>
          ))}
        </>
      ),
    },
  ];

  return (
    <Spin spinning={loading}>
      <div className="flex justify-end mb-3">
        <Button onClick={handleRebuild} loading={rebuilding}>
          {t('wiki.scan')}
        </Button>
      </div>
      <Row gutter={16} className="mb-4">
        <Col span={6}>
          <Card>
            <Statistic title={t('wiki.page')} value={insights.node_count || 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={t('wiki.edges')} value={insights.edge_count || 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={t('wiki.community')} value={insights.community_count || 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={t('wiki.largest')} value={insights.largest_community || 0} />
          </Card>
        </Col>
      </Row>
      {!!graph.nodes.length && (
        <Card className="mb-4" size="small">
          <GraphCanvas nodes={graph.nodes} edges={graph.edges} />
        </Card>
      )}
      <Card title={t('wiki.communities')} className="mb-4" size="small">
        <List
          size="small"
          dataSource={graph.communities || []}
          renderItem={(c, idx) => (
            <List.Item>
              <span className="mr-2 font-medium">#{idx + 1}</span>
              {c.map((id) => (
                <Tag key={id}>{titleOf(id)}</Tag>
              ))}
            </List.Item>
          )}
        />
      </Card>
      <Card title={t('wiki.strongestRelations')} size="small">
        {/* scroll x:undefined 关闭 CustomTable 默认强制的横向滚动,列宽自适应容器,消除底部多余横向滚动条 */}
        <CustomTable<GraphEdge>
          rowKey={(e) => `${e.from}-${e.to}`}
          columns={edgeColumns}
          dataSource={strongest}
          pagination={false}
          size="small"
          scroll={{ x: undefined }}
        />
      </Card>
    </Spin>
  );
};

export default GraphTab;
