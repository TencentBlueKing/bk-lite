'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button, Drawer, Dropdown, Empty, Input, Select, Space, Table, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import RefreshIconButton from '@/components/refresh-icon-button';
import TopSection from '@/components/top-section';
import { useTranslation } from '@/utils/i18n';
import { useGovernanceApi, useInstanceApi, useModelApi } from '@/app/cmdb/api';
import type { GovernanceOverview, GovernanceProblem } from '@/app/cmdb/api/governance';
import { buildBaseInfoPath } from '@/app/cmdb/(pages)/views/viewUrls';

type PathKey = 'all' | 'completeness' | 'freshness' | 'duplicate' | 'island';

const PATHS: PathKey[] = ['all', 'completeness', 'freshness', 'duplicate', 'island'];
const CONFIG_TAB: Record<Exclude<PathKey, 'all'>, string> = {
  completeness: 'attributes',
  freshness: 'attributes',
  duplicate: 'duplicateRules',
  island: 'associations',
};

const scoreClass = (score: number | null) => {
  if (score === null) return 'text-[var(--color-text-3)]';
  if (score >= 70) return 'text-[var(--color-success)]';
  if (score >= 30) return 'text-[var(--color-warning)]';
  return 'text-[var(--color-fail)]';
};

const formatScore = (score: number | null) => (score === null ? '—' : `${Number(score.toFixed(1))}%`);

const GovernancePage: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const path = (PATHS.includes(searchParams.get('path') as PathKey) ? searchParams.get('path') : 'all') as PathKey;
  const modelId = searchParams.get('model_id') || '';
  const organizationId = searchParams.get('organization_id') || '';
  const ruleId = searchParams.get('rule_id') || '';
  const keyword = searchParams.get('q') || '';
  const {
    getGovernanceOverview,
    getGovernanceProblems,
    refreshGovernance,
    ignoreGovernanceProblem,
    confirmGovernanceProblem,
    createGovernanceRelation,
    batchConfirmGovernanceProblems,
  } = useGovernanceApi();
  const { getModelList, getModelAssociations } = useModelApi();
  const { searchInstances } = useInstanceApi();
  const [overview, setOverview] = useState<GovernanceOverview | null>(null);
  const [problems, setProblems] = useState<GovernanceProblem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [models, setModels] = useState<Array<{ model_id: string; model_name: string }>>([]);
  const [selected, setSelected] = useState<GovernanceProblem | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [targets, setTargets] = useState<Array<{ id: number; inst_name: string }>>([]);
  const [targetId, setTargetId] = useState<number | undefined>();
  const [acting, setActing] = useState(false);

  const replaceQuery = (patch: Record<string, string>) => {
    const next = new URLSearchParams(searchParams.toString());
    Object.entries(patch).forEach(([key, value]) => {
      if (value) next.set(key, value);
      else next.delete(key);
    });
    router.replace(`/cmdb/assetManage/governance?${next.toString()}`);
  };

  const fetchGovernance = async (nextPage: number) => {
    const [overviewData, problemData] = await Promise.all([
      getGovernanceOverview({ model_id: modelId, organization_id: organizationId }),
      getGovernanceProblems({
        path,
        model_id: modelId,
        organization_id: organizationId,
        rule_id: ruleId,
        q: keyword,
        page: nextPage,
        page_size: 20,
      }),
    ]);
    setOverview(overviewData);
    setProblems(problemData.items || []);
    setTotal(problemData.count || 0);
  };

  const load = async (nextPage = page) => {
    setLoading(true);
    try {
      await fetchGovernance(nextPage);
    } finally {
      setLoading(false);
    }
  };

  const refresh = async () => {
    setRefreshing(true);
    try {
      await refreshGovernance({ model_id: modelId });
      message.success(t('Governance.refreshStarted'));
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    getModelList().then((data) => setModels(data || [])).catch(() => setModels([]));
  }, []);

  useEffect(() => {
    setPage(1);
    load(1);
  }, [path, modelId, organizationId, ruleId, keyword]);

  const openInstance = (problem: GovernanceProblem, member = problem.members[0]) => {
    if (!member?.inst_uuid) return;
    router.push(buildBaseInfoPath({
      model_id: problem.model_id,
      inst_uuid: member.inst_uuid,
      inst_name: member.inst_name,
      model_name: problem.model_name,
    }));
  };

  const openRelations = (problem: GovernanceProblem) => {
    const member = problem.members[0];
    if (!member?.inst_uuid) return;
    const base = buildBaseInfoPath({
      model_id: problem.model_id,
      inst_uuid: member.inst_uuid,
      inst_name: member.inst_name,
      model_name: problem.model_name,
    });
    router.push(base.replace('/baseInfo?', '/relationships?'));
  };

  const openProblem = async (problem: GovernanceProblem) => {
    setSelected(problem);
    setTargetId(undefined);
    setTargets([]);
    if (problem.problem_type !== 'island') return;
    const associations = await getModelAssociations(problem.model_id);
    const relation = (associations || []).find((item: { model_asst_id: string }) => item.model_asst_id === problem.rule_id);
    if (!relation?.dst_model_id) return;
    const result = await searchInstances({ model_id: relation.dst_model_id, page: 1, page_size: 20, query_list: [] }) as { insts?: Array<{ _id: number; inst_name: string }> };
    setTargets((result.insts || []).map((item) => ({ id: item._id, inst_name: item.inst_name })));
  };

  const runAction = async (action: () => Promise<unknown>) => {
    setActing(true);
    try {
      await action();
      setSelected(null);
      await load(page);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('Governance.empty'));
    } finally {
      setActing(false);
    }
  };

  const configure = (tab: string) => {
    if (!modelId) return;
    router.push(`/cmdb/assetManage/management/detail/${tab}?model_id=${modelId}`);
  };

  const columns: ColumnsType<GovernanceProblem> = [
    {
      title: t('Governance.object'),
      dataIndex: 'title',
      render: (_, record) => <span className="text-[var(--color-text-1)]">{record.title}</span>,
    },
    {
      title: t('Governance.detail'),
      dataIndex: 'detail',
    },
    {
      title: t('Governance.path'),
      dataIndex: 'problem_type',
      width: 140,
      render: (value: string) => <Tag>{t(`Governance.${value === 'uniqueness_conflict' ? 'uniquenessConflict' : value}`)}</Tag>,
    },
    {
      title: t('Governance.model'),
      dataIndex: 'model_name',
      width: 140,
      render: (_, record) => record.model_name || record.model_id,
    },
  ];

  const batchable = path === 'completeness' || path === 'freshness';
  const cards = useMemo(() => ([
    { key: 'all' as PathKey, label: t('Governance.overall'), value: formatScore(overview?.total_health_score ?? null), tone: scoreClass(overview?.total_health_score ?? null) },
    { key: 'completeness' as PathKey, label: t('Governance.completeness'), value: formatScore(overview?.completeness_score ?? null), tone: scoreClass(overview?.completeness_score ?? null) },
    { key: 'freshness' as PathKey, label: t('Governance.freshness'), value: formatScore(overview?.freshness_score ?? null), tone: scoreClass(overview?.freshness_score ?? null) },
    { key: 'duplicate' as PathKey, label: t('Governance.duplicate'), value: String(overview?.duplicate_group_count ?? 0), tone: (overview?.duplicate_group_count || 0) > 0 ? 'text-[var(--color-warning)]' : 'text-[var(--color-text-1)]' },
    { key: 'island' as PathKey, label: t('Governance.island'), value: String(overview?.island_instance_count ?? 0), tone: (overview?.island_instance_count || 0) > 0 ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-1)]' },
  ]), [overview, t]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--color-bg-1)] p-4">
      <TopSection
        title={t('Governance.title')}
        content={overview?.snapshot_date ? t('Governance.asOf', undefined, { date: overview.snapshot_date }) : t('Governance.noSnapshot')}
        extra={<RefreshIconButton loading={refreshing} onClick={refresh} />}
      />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
        {cards.map((card) => (
          <button
            key={card.key}
            type="button"
            aria-pressed={path === card.key}
            className={`rounded-md border-2 bg-[var(--color-bg)] px-4 py-3 text-left ${path === card.key ? 'border-[var(--color-primary)] bg-[color-mix(in_srgb,var(--color-primary)_8%,var(--color-bg))] shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-primary)_18%,transparent)]' : 'border-transparent'}`}
            onClick={() => {
              if (path !== card.key) replaceQuery({ path: card.key === 'all' ? '' : card.key });
            }}
          >
            <div className="text-xs text-[var(--color-text-3)]">{card.label}</div>
            <div className={`mt-1 text-2xl font-semibold ${card.tone} ${loading ? 'opacity-40' : ''}`}>{overview?.snapshot_date ? card.value : '—'}</div>
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 rounded-md bg-[var(--color-bg)] p-4">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-[var(--color-text-1)]">
            {t('Governance.currentMetric', undefined, { name: cards.find((card) => card.key === path)?.label || '' })}
          </span>
          <Select
            allowClear
            className="w-[220px]"
            placeholder={t('Governance.model')}
            value={modelId || undefined}
            options={models.map((item) => ({ value: item.model_id, label: item.model_name }))}
            onChange={(value) => replaceQuery({ model_id: value || '' })}
            showSearch
            optionFilterProp="label"
          />
          <Input.Search
            allowClear
            className="w-[240px]"
            placeholder={t('Governance.search')}
            defaultValue={keyword}
            onSearch={(value) => replaceQuery({ q: value })}
          />
          {organizationId && (
            <Tag closable onClose={() => replaceQuery({ organization_id: '' })}>
              {organizationId}
            </Tag>
          )}
          <div className="ml-auto flex items-center gap-2">
            {path === 'all' ? (
              <Dropdown
                disabled={!modelId}
                menu={{
                  items: [
                    { key: 'attributes', label: t('Governance.configureAttributes'), onClick: () => configure('attributes') },
                    { key: 'duplicateRules', label: t('Governance.configureDuplicate'), onClick: () => configure('duplicateRules') },
                    { key: 'associations', label: t('Governance.configureRelations'), onClick: () => configure('associations') },
                  ],
                }}
              >
                <Button disabled={!modelId}>{t('Governance.configure')}</Button>
              </Dropdown>
            ) : (
              <Button disabled={!modelId} onClick={() => configure(CONFIG_TAB[path])}>{t('Governance.configure')}</Button>
            )}
          </div>
        </div>
        {batchable && (
          <Space className="mb-3">
            {path === 'freshness' && (
              <Button
                disabled={!selectedRowKeys.length}
                onClick={() => runAction(() => batchConfirmGovernanceProblems(selectedRowKeys.map(Number)))}
              >
                {t('Governance.batchConfirm')}
              </Button>
            )}
            <Button onClick={() => router.push('/cmdb/assetManage/autoDiscovery/collection')}>{t('Governance.recollect')}</Button>
          </Space>
        )}
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={problems}
          locale={{ emptyText: <Empty description={overview?.snapshot_date ? t('Governance.empty') : t('Governance.noSnapshot')} /> }}
          rowSelection={batchable ? { selectedRowKeys, onChange: setSelectedRowKeys } : undefined}
          pagination={{ current: page, pageSize: 20, total, onChange: (next) => { setPage(next); load(next); } }}
          onRow={(record) => ({ onClick: () => openProblem(record) })}
        />
      </div>
      <Drawer
        width={520}
        open={Boolean(selected)}
        maskClosable
        title={selected?.title}
        onClose={() => setSelected(null)}
      >
        {selected && (
          <div className="flex flex-col gap-4">
            <div className="text-[var(--color-text-2)]">{selected.detail}</div>
            {selected.members.map((member) => (
              <button key={member.id} type="button" className="text-left text-[var(--color-primary)]" onClick={() => openInstance(selected, member)}>
                {member.inst_name || member.inst_uuid}
              </button>
            ))}
            {selected.hidden_member_count > 0 && (
              <div className="text-[var(--color-text-3)]">{t('Governance.hiddenMembers', undefined, { count: selected.hidden_member_count })}</div>
            )}
            <Space wrap>
              {selected.problem_type === 'duplicate' && selected.can_ignore && (
                <Button loading={acting} onClick={() => runAction(() => ignoreGovernanceProblem(selected.id))}>{t('Governance.ignoreGroup')}</Button>
              )}
              {selected.problem_type === 'freshness' && (
                <Button loading={acting} onClick={() => runAction(() => confirmGovernanceProblem(selected.id))}>{t('Governance.confirmValid')}</Button>
              )}
              {(selected.problem_type === 'completeness' || selected.problem_type === 'freshness') && (
                <>
                  <Button onClick={() => openInstance(selected)}>{t('Governance.editInstance')}</Button>
                  <Button onClick={() => router.push('/cmdb/assetManage/autoDiscovery/collection')}>{t('Governance.recollect')}</Button>
                </>
              )}
              {selected.problem_type === 'island' && (
                <>
                  <Select
                    className="min-w-[220px]"
                    placeholder={t('Governance.selectTarget')}
                    value={targetId}
                    options={targets.map((item) => ({ value: item.id, label: item.inst_name }))}
                    onChange={setTargetId}
                  />
                  <Button
                    type="primary"
                    disabled={!targetId}
                    loading={acting}
                    onClick={() => runAction(() => createGovernanceRelation(selected.id, targetId!))}
                  >
                    {t('Governance.createRelation')}
                  </Button>
                  <Button onClick={() => openRelations(selected)}>{t('Governance.openRelations')}</Button>
                </>
              )}
              {selected.problem_type !== 'island' && selected.members[0]?.inst_uuid && (
                <Button onClick={() => openInstance(selected)}>{t('Governance.openInstance')}</Button>
              )}
            </Space>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default GovernancePage;
