'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Card, Empty, List, Skeleton, Space, Spin, Statistic, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { WikiOverview } from '@/app/opspilot/types/wiki';
import WikiQaAssistant from './WikiQaAssistant';
import ContributionTag from './ContributionTag';
import { formatWikiTime, TRIGGER_LABEL, BUILD_STATUS_LABEL } from './wikiFormat';

const MAT_STATUS_META: Record<string, { color: string; key: string }> = {
  pending: { color: 'default', key: 'wiki.statusPending' },
  parsing: { color: 'processing', key: 'wiki.statusParsing' },
  done: { color: 'green', key: 'wiki.statusDone' },
  building: { color: 'processing', key: 'wiki.statusBuilding' },
  built: { color: 'green', key: 'wiki.statusBuilt' },
  failed: { color: 'red', key: 'wiki.statusFailed' },
};

// check_type → i18n key(只翻译 overview_service.py:13-18 里 4 个 open 决策型,
// 与后端 DB CheckConstraint 范围一致;其它取值回退显示原 key)
const CHECK_TYPE_LABEL: Record<string, string> = {
  conflict: 'wiki.checkConflict',
  duplicate: 'wiki.checkDuplicate',
  cannot_merge: 'wiki.checkCannotMerge',
  material_update: 'wiki.checkMaterialUpdate',
};

// 概览工作区(主内容 + 右半常驻问答栏)
const OverviewTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchOverview } = useWikiApi();
  const [data, setData] = useState<WikiOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const labelOf = (map: Record<string, string>, v: string) => (map[v] ? t(map[v]) : v || '--');

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
  const matStatus = data?.material_status || {};
  const checks = data?.checks_by_type || {};
  const recentBuilds = (data?.recent_builds || []) as Array<Record<string, unknown>>;
  const recentPages = (data?.recent_pages || []) as Array<Record<string, unknown>>;
  const agents = data?.agents || [];

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 lg:flex-row">
      {/* ── 主内容(左 1fr,内部独立滚动) ── */}
      <section className="min-h-0 min-w-0 flex-1 overflow-y-auto pr-1">
        <Spin spinning={loading}>
          {!data && !loading ? (
            <Empty className="py-12" />
          ) : !data ? (
            <OverviewSkeleton />
          ) : (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                <Card size="small">
                  <Statistic title={t('wiki.materialCount')} value={counts.materials || 0} />
                </Card>
                <Card size="small">
                  <Statistic title={t('wiki.pageCount')} value={counts.pages || 0} />
                </Card>
                <Card size="small">
                  <Statistic title={t('wiki.relations')} value={counts.relations || 0} />
                </Card>
                <Card size="small">
                  <Statistic
                    title={t('wiki.pendingReview')}
                    value={counts.open_checks || 0}
                    valueStyle={
                      counts.open_checks ? { color: 'var(--color-fail)' } : undefined
                    }
                  />
                </Card>
              </div>

              <Card size="small" title={t('wiki.processing')}>
                <Space wrap>
                  {Object.keys(matStatus).length === 0 && (
                    <span className="text-[var(--color-text-3)]">--</span>
                  )}
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

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <Card size="small" title={t('wiki.recentPages')}>
                  <List
                    size="small"
                    dataSource={recentPages}
                    renderItem={(p) => (
                      <List.Item>
                        <span className="mr-2 truncate">{String(p.title)}</span>
                        <ContributionTag value={String(p.contribution)} />
                      </List.Item>
                    )}
                  />
                </Card>
                <Card size="small" title={t('wiki.recentBuilds')}>
                  <List
                    size="small"
                    dataSource={recentBuilds}
                    renderItem={(b) => (
                      <List.Item>
                        <span className="mr-2 truncate">
                          {formatWikiTime(b.created_at as string)} ·{' '}
                          {labelOf(TRIGGER_LABEL, String(b.trigger))}
                        </span>
                        <Tag
                          color={
                            b.status === 'success'
                              ? 'green'
                              : b.status === 'failed'
                                ? 'red'
                                : 'blue'
                          }
                        >
                          {labelOf(BUILD_STATUS_LABEL, String(b.status))}
                        </Tag>
                      </List.Item>
                    )}
                  />
                </Card>
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <Card size="small" title={t('wiki.risks')}>
                  <Space wrap>
                    {Object.keys(checks).length === 0 && (
                      <span className="text-[var(--color-text-3)]">{t('wiki.noRisks')}</span>
                    )}
                    {Object.entries(checks).map(([type, c]) => (
                      <Tag color="gold" key={type}>
                        {t(CHECK_TYPE_LABEL[type] || type)}: {c}
                      </Tag>
                    ))}
                  </Space>
                </Card>
                <Card size="small" title={t('wiki.agents')}>
                  <Space wrap>
                    {agents.length === 0 && (
                      <span className="text-[var(--color-text-3)]">{t('wiki.noAgents')}</span>
                    )}
                    {agents.map((a) => (
                      <Tag color="blue" key={a.id}>
                        {a.name}
                      </Tag>
                    ))}
                  </Space>
                </Card>
              </div>
            </div>
          )}
        </Spin>
      </section>

      {/* ── 右半常驻问答栏 ── */}
      <aside className="h-full w-full shrink-0 lg:w-[400px]">
        <WikiQaAssistant kbId={kbId} mode="embedded" />
      </aside>
    </div>
  );
};

const OverviewSkeleton: React.FC = () => (
  <div className="flex flex-col gap-4">
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Card size="small" key={i}>
          <Skeleton active paragraph={{ rows: 1 }} title={false} />
        </Card>
      ))}
    </div>
    <Card size="small">
      <Skeleton active paragraph={{ rows: 2 }} title={false} />
    </Card>
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card size="small">
        <Skeleton active paragraph={{ rows: 4 }} title={false} />
      </Card>
      <Card size="small">
        <Skeleton active paragraph={{ rows: 4 }} title={false} />
      </Card>
    </div>
  </div>
);

export default OverviewTab;
