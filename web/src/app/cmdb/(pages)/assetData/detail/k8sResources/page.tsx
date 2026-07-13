'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Input, Select, Space, Spin, Tooltip } from 'antd';
import {
  AppstoreOutlined, ClusterOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  NodeIndexOutlined, ReloadOutlined, SearchOutlined,
} from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import { useK8sResourceApi } from './api';
import {
  getK8sResourceColumns, K8S_RESOURCE_NAV_ITEMS, K8sBranchData, K8sOverviewData,
  K8sResourceKind, K8sResourceSubView, K8sTopologyData, K8sTopologyNode,
  mergeTopologyBranch, PodBranchQueue,
} from './model';
import { K8sTopology } from './topology';
import styles from './styles.module.scss';
import { useTranslation } from '@/utils/i18n';
import { K8sResourceTable } from './resourceTable';

const branchQueue = new PodBranchQueue(4);
const branchCache = new Map<string, K8sBranchData>();
const WORKLOAD_KINDS = new Set(['deployment', 'statefulset', 'daemonset', 'job', 'cronjob']);
const NAV_ICON: Record<string, React.ReactNode> = {
  overview: <AppstoreOutlined />, namespace: <ClusterOutlined />, pod: <NodeIndexOutlined />, node: <NodeIndexOutlined />,
};

type BranchState = Record<string, { status: string; page: number; loaded: number; count: number; data?: K8sBranchData; error?: string }>;

const unwrap = <T,>(value: unknown): T => {
  const record = value as { data?: T };
  return (record?.data ?? value) as T;
};

export const K8sOverviewContent: React.FC<{
  data: K8sOverviewData;
  topology: K8sTopologyData;
  expanded: Set<string>;
  branches: BranchState;
  onToggleWorkload: (id: string) => void;
  onLoadMorePods: (id: string) => void;
  onLoadMoreLayer: (layer: 'namespace' | 'workload' | 'node') => void;
  onOpenList: (kind: string, node?: K8sTopologyNode) => void;
  unownedExpanded?: boolean;
  unownedLoading?: boolean;
  onToggleUnowned?: () => void;
}> = ({ data, topology, expanded, branches, onToggleWorkload, onLoadMorePods, onLoadMoreLayer, onOpenList, unownedExpanded, unownedLoading, onToggleUnowned }) => {
  const { t } = useTranslation();
  const metrics = [
    { label: t('K8sResourceOverview.metrics.namespace'), value: data.summary.namespace_count },
    { label: t('K8sResourceOverview.metrics.workload'), value: data.summary.workload_count, detail: t('K8sResourceOverview.metrics.otherWorkload', undefined, { count: data.summary.other_workload_count }) },
    { label: t('K8sResourceOverview.metrics.pod'), value: data.summary.pod_count },
    { label: t('K8sResourceOverview.metrics.node'), value: data.summary.node_count },
  ];
  return <>
    <div className={styles.metricGrid}>
      {metrics.map(({ label, value, detail }) => <div className={styles.metricCard} key={label}>
        <div className={styles.metricLabel}>{label}</div><div className={styles.metricValue}>{value}</div>
        {detail && <div className={styles.metricDetail}>{detail}</div>}
      </div>)}
    </div>
    <div className={styles.topologyCard}>
      <K8sTopology
        topology={topology}
        expandedWorkloads={expanded}
        branchMeta={Object.fromEntries(Object.entries(branches).map(([key, value]) => [key, value]))}
        layers={data.layers}
        onToggleWorkload={onToggleWorkload}
        onLoadMorePods={onLoadMorePods}
        onLoadMoreLayer={onLoadMoreLayer}
        onOpenList={onOpenList}
        unownedExpanded={unownedExpanded}
        unownedLoading={unownedLoading}
        onToggleUnowned={onToggleUnowned}
      />
    </div>
  </>;
};

const K8sResourceDetails = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const api = useK8sResourceApi();
  const clusterId = searchParams.get('inst_id') || '';
  const requestedSub = searchParams.get('sub') as K8sResourceSubView | null;
  const sub = K8S_RESOURCE_NAV_ITEMS.some((item) => item.key === requestedSub) ? requestedSub! : 'overview';
  const [overview, setOverview] = useState<K8sOverviewData | null>(null);
  const [baseTopology, setBaseTopology] = useState<K8sTopologyData>({ nodes: [], edges: [] });
  const [branches, setBranches] = useState<BranchState>({});
  const [unownedBranch, setUnownedBranch] = useState<K8sBranchData | null>(null);
  const [unownedExpanded, setUnownedExpanded] = useState(searchParams.get('unowned_pods') === '1');
  const [unownedLoading, setUnownedLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(
    (searchParams.get('expanded_workloads') || '').split(',').filter(Boolean)
  ));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [manualCollapsed, setManualCollapsed] = useState<boolean>(() =>
    typeof window !== 'undefined' && sessionStorage.getItem('cmdb-k8s-nav-collapsed') === '1'
  );
  const [narrow, setNarrow] = useState(false);
  const [overlayOpen, setOverlayOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const restoredClusterRef = useRef('');

  const loadOverview = useCallback(async (invalidate = false) => {
    if (!clusterId) return;
    setLoading(true); setError('');
    if (invalidate) {
      [...branchCache.keys()].filter((key) => key.startsWith(`${clusterId}:`)).forEach((key) => branchCache.delete(key));
      setBranches({}); setExpanded(new Set());
      setUnownedBranch(null); setUnownedExpanded(false);
      const params = new URLSearchParams(searchParams);
      params.delete('expanded_workloads');
      params.delete('unowned_pods');
      router.replace(`?${params.toString()}`);
    }
    try {
      const data = unwrap<K8sOverviewData>(await api.getOverview(clusterId));
      setOverview(data); setBaseTopology(data.topology);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('K8sResourceOverview.states.overviewError'));
    } finally { setLoading(false); }
  }, [api, clusterId]);

  useEffect(() => { loadOverview(); }, [clusterId]);
  useEffect(() => {
    const element = rootRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setNarrow(entry.contentRect.width - 220 < 1100));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const requestBranch = useCallback(async (workloadId: string, page: number) => {
    const cacheKey = `${clusterId}:${workloadId}`;
    const cached = branchCache.get(cacheKey);
    if (page === 1 && cached) {
      setBranches((value) => ({ ...value, [workloadId]: { status: 'loaded', page: cached.page, loaded: cached.nodes.filter((n) => n.layer === 'pod').length, count: cached.count, data: cached } }));
      return;
    }
    setBranches((value) => ({ ...value, [workloadId]: { ...value[workloadId], status: 'waiting', page, loaded: value[workloadId]?.loaded || 0, count: value[workloadId]?.count || 0 } }));
    try {
      const result = await branchQueue.enqueue(workloadId, async () => {
        setBranches((value) => ({ ...value, [workloadId]: { ...value[workloadId], status: 'loading' } }));
        return unwrap<K8sBranchData>(await api.getWorkloadPods(clusterId, workloadId, page));
      });
      const previous = page > 1 ? branchCache.get(cacheKey) : undefined;
      const data: K8sBranchData = previous
        ? { ...result, ...mergeTopologyBranch(previous, result), page: result.page }
        : result;
      branchCache.set(cacheKey, data);
      setBranches((value) => ({ ...value, [workloadId]: {
        status: 'loaded', page: data.page, loaded: data.nodes.filter((node) => node.layer === 'pod').length,
        count: data.count, data,
      } }));
    } catch (reason) {
      setBranches((value) => ({ ...value, [workloadId]: { ...value[workloadId], status: 'error', error: reason instanceof Error ? reason.message : t('K8sResourceOverview.states.podError') } }));
    }
  }, [api, clusterId]);

  useEffect(() => {
    if (!overview || restoredClusterRef.current === clusterId) return;
    restoredClusterRef.current = clusterId;
    const workloadIds = new Set(overview.topology.nodes.filter((node) => node.layer === 'workload').map((node) => node.id));
    const restored = [...expanded].filter((id) => workloadIds.has(id));
    setExpanded(new Set(restored));
    restored.forEach((id) => requestBranch(id, 1));
  }, [overview, clusterId]);

  const toggleWorkload = (id: string) => {
    const opening = !expanded.has(id);
    const next = new Set(expanded);
    if (opening) next.add(id); else next.delete(id);
    setExpanded(next);
    const params = new URLSearchParams(searchParams);
    if (next.size) params.set('expanded_workloads', [...next].join(','));
    else params.delete('expanded_workloads');
    router.replace(`?${params.toString()}`);
    if (opening) requestBranch(id, 1);
    else branchQueue.cancelWaiting(id);
  };

  const topology = useMemo(() => {
    let result = baseTopology;
    expanded.forEach((id) => { if (branches[id]?.data) result = mergeTopologyBranch(result, branches[id].data!); });
    if (unownedExpanded && unownedBranch) result = mergeTopologyBranch(result, unownedBranch);
    return result;
  }, [baseTopology, branches, expanded, unownedBranch, unownedExpanded]);

  const toggleUnowned = async () => {
    const opening = !unownedExpanded;
    setUnownedExpanded(opening);
    const params = new URLSearchParams(searchParams);
    if (opening) params.set('unowned_pods', '1'); else params.delete('unowned_pods');
    router.replace(`?${params.toString()}`);
    if (!opening || unownedBranch) return;
    setUnownedLoading(true);
    try { setUnownedBranch(unwrap<K8sBranchData>(await api.getUnownedPods(clusterId, 1))); }
    catch (reason) { setError(reason instanceof Error ? reason.message : t('K8sResourceOverview.states.unownedError')); }
    finally { setUnownedLoading(false); }
  };

  useEffect(() => {
    if (!overview || !unownedExpanded || unownedBranch || unownedLoading) return;
    setUnownedLoading(true);
    api.getUnownedPods(clusterId, 1)
      .then((result) => setUnownedBranch(unwrap<K8sBranchData>(result)))
      .catch((reason) => setError(reason instanceof Error ? reason.message : t('K8sResourceOverview.states.unownedError')))
      .finally(() => setUnownedLoading(false));
  }, [overview]);

  const loadMoreLayer = async (layer: 'namespace' | 'workload' | 'node') => {
    if (!overview) return;
    const state = overview.layers[layer];
    const page = Math.floor(state.shown / state.page_size) + 1;
    const namespaceIds = baseTopology.nodes.filter((node) => node.layer === 'namespace').map((node) => node.id);
    try {
      const result = unwrap<K8sBranchData>(await api.getLayer(clusterId, layer, page, layer === 'workload' ? namespaceIds : undefined));
      const nextTopology = mergeTopologyBranch(baseTopology, result);
      setBaseTopology(nextTopology);
      setOverview((value) => value ? ({ ...value, layers: { ...value.layers, [layer]: { ...value.layers[layer], shown: value.layers[layer].shown + result.nodes.length } } }) : value);
      if (layer === 'namespace') {
        const loadedNamespaceIds = nextTopology.nodes.filter((node) => node.layer === 'namespace').map((node) => node.id);
        const workloadProbe = unwrap<K8sBranchData>(await api.getLayer(clusterId, 'workload', 1, loadedNamespaceIds));
        setOverview((value) => value ? ({ ...value, layers: { ...value.layers, workload: { ...value.layers.workload, count: workloadProbe.count } } }) : value);
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('K8sResourceOverview.states.failed')); }
  };

  const navigate = (nextSub: string, filters: Record<string, string> = {}) => {
    const params = new URLSearchParams(searchParams);
    params.set('sub', nextSub);
    ['namespace_id', 'workload_id', 'node_id'].forEach((key) => params.delete(key));
    Object.entries(filters).forEach(([key, value]) => params.set(key, value));
    router.replace(`?${params.toString()}`);
    setOverlayOpen(false);
  };

  const openList = (kind: string, node?: K8sTopologyNode) => {
    const filters: Record<string, string> = {};
    let target = kind;
    if (kind === 'workload') target = node?.workload_type && WORKLOAD_KINDS.has(node.workload_type) ? node.workload_type : 'other_workload';
    if (node?.layer === 'namespace') filters.namespace_id = node.id;
    if (node?.layer === 'workload') filters.workload_id = node.id;
    if (node?.layer === 'node') filters.node_id = node.id;
    navigate(target, filters);
  };

  const collapsed = narrow ? !overlayOpen : manualCollapsed;
  const setCollapsed = () => {
    if (narrow) { setOverlayOpen((value) => !value); return; }
    setManualCollapsed((value) => { sessionStorage.setItem('cmdb-k8s-nav-collapsed', value ? '0' : '1'); return !value; });
  };

  return <div ref={rootRef} className={styles.page}>
    <aside className={`${styles.secondaryNav} ${collapsed ? styles.collapsed : ''} ${narrow && overlayOpen ? styles.overlay : ''}`}>
      <div className={styles.navHeader}>
        {!collapsed && <span>{t('K8sResourceOverview.title')}</span>}
        <Tooltip title={t(collapsed ? 'K8sResourceOverview.actions.expandNav' : 'K8sResourceOverview.actions.collapseNav')}><Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={setCollapsed} /></Tooltip>
      </div>
      {K8S_RESOURCE_NAV_ITEMS.map((item, index) => <React.Fragment key={item.key}>
        {!collapsed && item.group !== 'base' && K8S_RESOURCE_NAV_ITEMS[index - 1]?.group !== item.group && (
          <div className={styles.navGroup}>{t(`K8sResourceOverview.navGroups.${item.group}`)}</div>
        )}
        <Tooltip placement="right" title={collapsed ? t(`K8sResourceOverview.nav.${item.key}`, item.label) : undefined}>
          <button className={`${styles.navItem} ${sub === item.key ? styles.active : ''}`} onClick={() => navigate(item.key)}>
            <span>{NAV_ICON[item.key] || <ClusterOutlined />}</span>{!collapsed && <span>{t(`K8sResourceOverview.nav.${item.key}`, item.label)}</span>}
          </button>
        </Tooltip>
      </React.Fragment>)}
    </aside>
    <main className={`${styles.content} ${sub !== 'overview' ? styles.listContent : ''}`}>
      <div className={styles.toolbar}>
        <h1 className={styles.pageTitle}>{t(`K8sResourceOverview.nav.${sub}`, t('K8sResourceOverview.resourceDetails'))}</h1>
        {sub === 'overview' && <Button icon={<ReloadOutlined />} onClick={() => loadOverview(true)}>{t('K8sResourceOverview.actions.refresh')}</Button>}
      </div>
      {error && <Alert type="error" showIcon message={error} action={<Button size="small" onClick={() => loadOverview()}>{t('K8sResourceOverview.actions.retry')}</Button>} className="mb-3" />}
      <Spin spinning={loading} wrapperClassName={sub !== 'overview' ? styles.listSpin : undefined}>
        {sub === 'overview' && overview && <K8sOverviewContent
          data={overview} topology={topology} expanded={expanded} branches={branches}
          onToggleWorkload={toggleWorkload}
          onLoadMorePods={(id) => requestBranch(id, (branches[id]?.page || 0) + 1)}
          onLoadMoreLayer={loadMoreLayer} onOpenList={openList}
          unownedExpanded={unownedExpanded} unownedLoading={unownedLoading} onToggleUnowned={toggleUnowned}
        />}
        {sub !== 'overview' && <K8sResourceList clusterId={clusterId} kind={sub} api={api} searchParams={searchParams} router={router} />}
      </Spin>
    </main>
  </div>;
};

const K8sResourceList: React.FC<{ clusterId: string; kind: K8sResourceKind; api: ReturnType<typeof useK8sResourceApi>; searchParams: URLSearchParams; router: ReturnType<typeof useRouter> }> = ({ clusterId, kind, api, searchParams, router }) => {
  const { t } = useTranslation();
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState('');
  const [order, setOrder] = useState('name');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filterOptions, setFilterOptions] = useState<Record<string, Array<{ label: string; value: string }>>>({});
  const namespaceFilter = searchParams.get('namespace_id') || undefined;
  const workloadFilter = searchParams.get('workload_id') || undefined;
  const nodeFilter = searchParams.get('node_id') || undefined;
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const result = unwrap<{ items: Record<string, unknown>[]; count: number }>(await api.getResources(clusterId, kind, {
        page, pageSize, search, order,
        namespaceId: namespaceFilter,
        workloadId: workloadFilter,
        nodeId: nodeFilter,
      }));
      setItems(result.items); setCount(result.count);
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('K8sResourceOverview.states.listError')); }
    finally { setLoading(false); }
  }, [api, clusterId, kind, page, pageSize, search, order, namespaceFilter, workloadFilter, nodeFilter]);
  useEffect(() => { load(); }, [kind, page, pageSize, order, namespaceFilter, workloadFilter, nodeFilter]);
  useEffect(() => {
    if (!['deployment', 'statefulset', 'daemonset', 'job', 'cronjob', 'other_workload', 'pod'].includes(kind)) return;
    const toOptions = (result: unknown) => unwrap<{ items: Array<{ id: string; name: string }> }>(result).items.map((item) => ({ label: item.name, value: item.id }));
    const requests: Array<Promise<void>> = [
      api.getResources(clusterId, 'namespace', { pageSize: 500 }).then((result) => setFilterOptions((value) => ({ ...value, namespace: toOptions(result) }))),
    ];
    if (kind === 'pod') {
      requests.push(api.getResources(clusterId, 'node', { pageSize: 500 }).then((result) => setFilterOptions((value) => ({ ...value, node: toOptions(result) }))));
      requests.push(Promise.all(
        (['deployment', 'statefulset', 'daemonset', 'job', 'cronjob', 'other_workload'] as K8sResourceKind[])
          .map((workloadKind) => api.getResources(clusterId, workloadKind, { pageSize: 500 }))
      ).then((results) => setFilterOptions((value) => ({ ...value, workload: results.flatMap(toOptions) }))));
    }
    Promise.allSettled(requests);
  }, [clusterId, kind]);
  const modelId = kind === 'namespace' ? 'k8s_namespace' : kind === 'pod' ? 'k8s_pod' : kind === 'node' ? 'k8s_node' : 'k8s_workload';
  const columns = getK8sResourceColumns(kind).map((column) => ({
    title: t(`K8sResourceOverview.columns.${column.key}`, column.title), dataIndex: column.key, key: column.key, sorter: true,
    render: (value: unknown, record: Record<string, unknown>) => {
      if (column.key !== 'name') {
        return value === null || value === undefined || value === ''
          ? t('K8sResourceOverview.states.noData')
          : String(value);
      }
      const params = new URLSearchParams(searchParams);
      params.set('model_id', modelId);
      params.set('inst_id', String(record.id));
      params.set('inst_name', String(value || ''));
      const detailUrl = `/cmdb/assetData/detail/baseInfo?${params.toString()}`;
      return <a href={detailUrl} target="_blank" rel="noopener noreferrer">
        {String(value || t('K8sResourceOverview.states.noData'))}
      </a>;
    },
  }));
  const setFilter = (key: string, value?: string) => {
    const params = new URLSearchParams(searchParams);
    if (value) params.set(key, value); else params.delete(key);
    router.replace(`?${params.toString()}`);
    setPage(1);
  };
  return <div className={styles.resourceList}>
    <div className={styles.toolbar}>
      <Space wrap>
        <Input.Search allowClear value={search} onChange={(e) => setSearch(e.target.value)} onSearch={() => { if (page === 1) load(); else setPage(1); }} prefix={<SearchOutlined />} placeholder={t('K8sResourceOverview.list.search')} style={{ width: 260 }} />
        {filterOptions.namespace && <Select allowClear showSearch optionFilterProp="label" placeholder={t('K8sResourceOverview.list.namespaceFilter')} value={namespaceFilter} options={filterOptions.namespace} style={{ width: 180 }} onChange={(value) => setFilter('namespace_id', value)} />}
        {kind === 'pod' && <Select allowClear showSearch optionFilterProp="label" placeholder={t('K8sResourceOverview.list.workloadFilter')} value={workloadFilter} options={filterOptions.workload} style={{ width: 200 }} onChange={(value) => setFilter('workload_id', value)} />}
        {kind === 'pod' && <Select allowClear showSearch optionFilterProp="label" placeholder={t('K8sResourceOverview.list.nodeFilter')} value={nodeFilter} options={filterOptions.node} style={{ width: 180 }} onChange={(value) => setFilter('node_id', value)} />}
      </Space>
      <Button icon={<ReloadOutlined />} onClick={load}>{t('K8sResourceOverview.actions.refresh')}</Button>
    </div>
    {error && <Alert type="error" showIcon message={error} action={<Button size="small" onClick={load}>{t('K8sResourceOverview.actions.retry')}</Button>} className="mb-3" />}
    <div className={styles.tableShell}>
      <K8sResourceTable
        items={items}
        columns={columns}
        loading={loading}
        page={page}
        pageSize={pageSize}
        count={count}
        onPageChange={(nextPage, nextPageSize) => {
          setPage(nextPageSize === pageSize ? nextPage : 1);
          setPageSize(nextPageSize);
        }}
        onSortChange={(field, descending) => setOrder(`${descending ? '-' : ''}${field}`)}
      />
    </div>
  </div>;
};

export default K8sResourceDetails;
