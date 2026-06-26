'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Card, Col, Empty, List, Row, Space, Spin, Statistic, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { WikiOverview } from '@/app/opspilot/types/wiki';
import WikiQaAssistant from './WikiQaAssistant';

const MAT_STATUS_META: Record<string, { color: string; key: string }> = {
  pending: { color: 'default', key: 'wiki.statusPending' },
  parsing: { color: 'processing', key: 'wiki.statusParsing' },
  done: { color: 'green', key: 'wiki.statusDone' },
  building: { color: 'processing', key: 'wiki.statusBuilding' },
  built: { color: 'green', key: 'wiki.statusBuilt' },
  failed: { color: 'red', key: 'wiki.statusFailed' },
};

// 概览工作区(spec 4.1):健康摘要 + 处理/异常 + 最近知识/构建 + 风险 + 使用的智能体 + 问答试用
const OverviewTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchOverview } = useWikiApi();
  const [data, setData] = useState<WikiOverview | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchOverview(kbId));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const counts = data?.counts || {};
  const health = (data?.health || {}) as Record<string, number>;
  const matStatus = data?.material_status || {};
  const checks = data?.checks_by_type || {};
  const recentBuilds = (data?.recent_builds || []) as Array<Record<string, unknown>>;
  const recentPages = (data?.recent_pages || []) as Array<Record<string, unknown>>;
  const agents = data?.agents || [];
  const coverage = Number(health.source_coverage || 0);

  return (
    <Spin spinning={loading}>
      {!data ? (
        <Empty />
      ) : (
        <>
          <Row gutter={16} className="mb-4">
            <Col span={5}>
              <Card size="small">
                <Statistic title={t('wiki.material')} value={counts.materials || 0} />
              </Card>
            </Col>
            <Col span={5}>
              <Card size="small">
                <Statistic title={t('wiki.page')} value={counts.pages || 0} />
              </Card>
            </Col>
            <Col span={5}>
              <Card size="small">
                <Statistic title={t('wiki.sourceCoverage')} value={coverage} suffix="%" />
              </Card>
            </Col>
            <Col span={5}>
              <Card size="small">
                <Statistic title={t('wiki.relations')} value={counts.relations || 0} />
              </Card>
            </Col>
            <Col span={4}>
              <Card size="small">
                <Statistic
                  title={t('wiki.check')}
                  value={counts.open_checks || 0}
                  valueStyle={counts.open_checks ? { color: 'var(--color-fail)' } : undefined}
                />
              </Card>
            </Col>
          </Row>

          <Card size="small" title={t('wiki.processing')} className="mb-4">
            <Space wrap>
              {Object.keys(matStatus).length === 0 && <span className="text-[var(--color-text-3)]">--</span>}
              {Object.entries(matStatus).map(([s, c]) => {
                const meta = MAT_STATUS_META[s];
                return (
                  <Tag key={s} color={meta?.color || 'default'}>
                    {(meta ? t(meta.key) : s)}: {c}
                  </Tag>
                );
              })}
            </Space>
          </Card>

          <Row gutter={16} className="mb-4">
            <Col span={12}>
              <Card size="small" title={t('wiki.recentPages')}>
                <List
                  size="small"
                  dataSource={recentPages}
                  renderItem={(p) => (
                    <List.Item>
                      <span className="truncate mr-2">{String(p.title)}</span>
                      <Tag>{String(p.contribution)}</Tag>
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small" title={t('wiki.recentBuilds')}>
                <List
                  size="small"
                  dataSource={recentBuilds}
                  renderItem={(b) => (
                    <List.Item>
                      <span className="mr-2">
                        #{String(b.id)} · {String(b.trigger)}
                      </span>
                      <Tag color={b.status === 'success' ? 'green' : b.status === 'failed' ? 'red' : 'blue'}>
                        {String(b.status)}
                      </Tag>
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={16} className="mb-4">
            <Col span={12}>
              <Card size="small" title={t('wiki.risks')}>
                <Space wrap>
                  {Object.keys(checks).length === 0 && (
                    <span className="text-[var(--color-text-3)]">{t('wiki.noRisks')}</span>
                  )}
                  {Object.entries(checks).map(([type, c]) => (
                    <Tag color="gold" key={type}>
                      {type}: {c}
                    </Tag>
                  ))}
                </Space>
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small" title={t('wiki.agents')}>
                <Space wrap>
                  {agents.length === 0 && <span className="text-[var(--color-text-3)]">{t('wiki.noAgents')}</span>}
                  {agents.map((a) => (
                    <Tag color="blue" key={a.id}>
                      {a.name}
                    </Tag>
                  ))}
                </Space>
              </Card>
            </Col>
          </Row>
        </>
      )}
      {/* 问答试用:改为右下悬浮智能助手,默认不展示,点击展开对话弹窗(更省版面、样式更统一) */}
      <WikiQaAssistant kbId={kbId} />
    </Spin>
  );
};

export default OverviewTab;
