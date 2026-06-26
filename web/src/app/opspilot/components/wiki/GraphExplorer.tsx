'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Checkbox, Empty, Slider, Tooltip } from 'antd';
import {
  AimOutlined,
  ApartmentOutlined,
  BulbOutlined,
  CloseOutlined,
  FilterOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  MinusOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { GraphEdge, GraphNode, WikiGraph } from '@/app/opspilot/types/wiki';
import GraphCanvas, { GraphCanvasHandle, communityColor } from '@/app/opspilot/components/wiki/GraphCanvas';

interface GraphExplorerProps {
  graph: WikiGraph;
  titleOf: (id: number) => string;
  onRebuild?: () => void;
  rebuilding?: boolean;
  // 初始展开哪些浮层(主要给 Storybook 出不同版式预览;实际页面默认只开图例)
  initialPanels?: { filter?: boolean; insights?: boolean; legend?: boolean };
  // 非全屏时的容器高度(CSS 值),默认按页面留白计算;Storybook 可传 '100vh' 等铺满
  height?: string;
}

const panelCls =
  'absolute z-20 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] shadow-lg';
const chipCls =
  'inline-flex items-center rounded-full bg-[var(--color-fill-2)] px-2 py-0.5 text-xs text-[var(--color-text-2)]';

const GraphExplorer: React.FC<GraphExplorerProps> = ({
  graph,
  titleOf,
  onRebuild,
  rebuilding,
  initialPanels,
  height,
}) => {
  const { t } = useTranslation();
  const canvasRef = useRef<GraphCanvasHandle>(null);

  const [showFilter, setShowFilter] = useState(initialPanels?.filter ?? false);
  const [showInsights, setShowInsights] = useState(initialPanels?.insights ?? false);
  const [showLegend, setShowLegend] = useState(initialPanels?.legend ?? true);
  const [fullscreen, setFullscreen] = useState(false);

  const [nodeScale, setNodeScale] = useState(100); // 百分比,100% = 默认;实时原地改尺寸(不重排)
  const [spacing, setSpacing] = useState(100); // 已应用的间距(映射到 linkDistance),仅松手时更新
  const [spacingInput, setSpacingInput] = useState(100); // 拖动中的显示值(松手前不触发重排)
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const [hideIsolated, setHideIsolated] = useState(false);

  // ESC 退出全屏
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setFullscreen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [fullscreen]);

  // 各页面类型及数量(过滤器按类型筛选)
  const typeCounts = useMemo(() => {
    const m = new Map<string, number>();
    graph.nodes.forEach((n) => {
      const k = n.page_type || 'other';
      m.set(k, (m.get(k) || 0) + 1);
    });
    return Array.from(m.entries()).map(([type, count]) => ({ type, count }));
  }, [graph.nodes]);

  // 过滤后的节点/边
  const shownNodes = useMemo(() => {
    let ns = graph.nodes.filter((n) => !hiddenTypes.has(n.page_type || 'other'));
    if (hideIsolated) {
      const connected = new Set<number>();
      graph.edges.forEach((e) => {
        connected.add(e.from);
        connected.add(e.to);
      });
      ns = ns.filter((n) => connected.has(n.id));
    }
    return ns;
  }, [graph.nodes, graph.edges, hiddenTypes, hideIsolated]);
  const shownIds = useMemo(() => new Set(shownNodes.map((n) => n.id)), [shownNodes]);
  const shownEdges = useMemo(
    () => graph.edges.filter((e) => shownIds.has(e.from) && shownIds.has(e.to)),
    [graph.edges, shownIds]
  );
  const hiddenCount = graph.nodes.length - shownNodes.length;

  // 社区图例:以社区内连接度最高的节点标题作为该社区的代表名
  const legend = useMemo(() => {
    const deg = new Map<number, number>();
    graph.edges.forEach((e) => {
      deg.set(e.from, (deg.get(e.from) || 0) + 1);
      deg.set(e.to, (deg.get(e.to) || 0) + 1);
    });
    const byComm = new Map<number, GraphNode[]>();
    shownNodes.forEach((n) => {
      const c = n.community ?? 0;
      if (!byComm.has(c)) byComm.set(c, []);
      byComm.get(c)!.push(n);
    });
    return Array.from(byComm.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([c, list]) => {
        const hub = [...list].sort((x, y) => (deg.get(y.id) || 0) - (deg.get(x.id) || 0))[0];
        return { community: c, label: hub?.title || `${t('wiki.communities')} ${c + 1}`, count: list.length };
      });
  }, [shownNodes, graph.edges, t]);

  const ins = (graph.insights || {}) as Record<string, number>;
  const strongest = ((graph.insights?.strongest_edges as GraphEdge[] | undefined) || []).slice(0, 6);

  const toggleType = (type: string) =>
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  const resetFilters = () => {
    setNodeScale(100);
    setSpacing(100);
    setSpacingInput(100);
    setHiddenTypes(new Set());
    setHideIsolated(false);
  };

  const toggleBtn = (active: boolean, icon: React.ReactNode, label: string, onClick: () => void) => (
    <Tooltip title={label}>
      <Button size="small" type={active ? 'primary' : 'default'} icon={icon} onClick={onClick}>
        {label}
      </Button>
    </Tooltip>
  );

  return (
    <div
      className={
        fullscreen
          ? 'fixed inset-0 z-[1000] bg-[var(--color-bg-1)]'
          : 'relative w-full min-h-[480px] overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)]'
      }
      style={fullscreen ? undefined : { height: height ?? 'calc(100vh - 210px)' }}
    >
      {/* 图谱铺满 */}
      <div className="absolute inset-0">
        {shownNodes.length ? (
          <GraphCanvas
            ref={canvasRef}
            nodes={shownNodes}
            edges={shownEdges}
            height="100%"
            nodeScale={nodeScale / 100}
            linkDistance={Math.round((spacing / 100) * 160)}
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <Empty />
          </div>
        )}
      </div>

      {/* 顶部工具条 */}
      <div className="pointer-events-none absolute left-3 right-3 top-3 flex items-start justify-between gap-2">
        <div className="pointer-events-auto flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1.5 font-medium text-[var(--color-text-1)]">
            <ApartmentOutlined className="text-[var(--color-primary)]" />
            {t('wiki.graph')}
          </span>
          <span className={chipCls}>
            {shownNodes.length}/{graph.nodes.length} {t('wiki.page')}
          </span>
          <span className={chipCls}>
            {shownEdges.length}/{graph.edges.length} {t('wiki.edges')}
          </span>
          {hiddenCount > 0 && (
            <span className="inline-flex items-center rounded-full bg-[var(--color-primary-bg)] px-2 py-0.5 text-xs text-[var(--color-primary)]">
              {hiddenCount} {t('wiki.hidden')}
            </span>
          )}
        </div>
        <div className="pointer-events-auto flex items-center gap-1.5">
          {toggleBtn(showFilter, <FilterOutlined />, t('wiki.filters'), () => setShowFilter((v) => !v))}
          {toggleBtn(showLegend, <ApartmentOutlined />, t('wiki.communities'), () => setShowLegend((v) => !v))}
          {toggleBtn(showInsights, <BulbOutlined />, t('wiki.insights'), () => setShowInsights((v) => !v))}
          {onRebuild && (
            <Tooltip title={t('wiki.scan')}>
              <Button size="small" icon={<ReloadOutlined />} loading={rebuilding} onClick={onRebuild}>
                {t('wiki.scan')}
              </Button>
            </Tooltip>
          )}
        </div>
      </div>

      {/* 缩放 / 全屏 控件(右下) */}
      <div className="absolute bottom-3 right-3 z-20 flex flex-col gap-1.5">
        <Tooltip title={t('wiki.zoomIn')} placement="left">
          <Button shape="circle" icon={<PlusOutlined />} onClick={() => canvasRef.current?.zoomBy(1.2)} />
        </Tooltip>
        <Tooltip title={t('wiki.zoomOut')} placement="left">
          <Button shape="circle" icon={<MinusOutlined />} onClick={() => canvasRef.current?.zoomBy(0.83)} />
        </Tooltip>
        <Tooltip title={t('wiki.resetView')} placement="left">
          <Button shape="circle" icon={<AimOutlined />} onClick={() => canvasRef.current?.resetView()} />
        </Tooltip>
        <Tooltip title={fullscreen ? t('wiki.exitFullscreen') : t('wiki.fullscreen')} placement="left">
          <Button
            shape="circle"
            type={fullscreen ? 'primary' : 'default'}
            icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
            onClick={() => setFullscreen((v) => !v)}
          />
        </Tooltip>
      </div>

      {/* 过滤器面板(左上) */}
      {showFilter && (
        <div className={`${panelCls} left-3 top-14 w-[260px] p-3`}>
          <div className="mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-sm font-medium text-[var(--color-text-1)]">
              <FilterOutlined /> {t('wiki.filters')}
            </span>
            <Button type="link" size="small" className="px-0" onClick={resetFilters}>
              {t('wiki.reset')}
            </Button>
          </div>
          <div className="mb-1 flex items-center justify-between text-xs text-[var(--color-text-3)]">
            <span>{t('wiki.nodeSize')}</span>
            <span>{nodeScale}%</span>
          </div>
          <Slider min={60} max={140} value={nodeScale} onChange={setNodeScale} tooltip={{ open: false }} />
          <div className="mb-1 flex items-center justify-between text-xs text-[var(--color-text-3)]">
            <span>{t('wiki.spacing')}</span>
            <span>{spacingInput}%</span>
          </div>
          {/* 拖动只改显示值;松手(onChangeComplete)才更新间距 → 仅重排一次,避免拖动中持续重排 */}
          <Slider
            min={60}
            max={160}
            value={spacingInput}
            onChange={setSpacingInput}
            onChangeComplete={(v) => setSpacing(v as number)}
            tooltip={{ open: false }}
          />
          <div className="mb-1 mt-2 text-xs text-[var(--color-text-3)]">{t('wiki.nodeTypes')}</div>
          <div className="grid grid-cols-2 gap-x-2 gap-y-1">
            {typeCounts.map(({ type, count }) => (
              <Checkbox
                key={type}
                checked={!hiddenTypes.has(type)}
                onChange={() => toggleType(type)}
                className="!ml-0 text-xs"
              >
                <span className="text-[var(--color-text-2)]">
                  {type} <span className="text-[var(--color-text-3)]">{count}</span>
                </span>
              </Checkbox>
            ))}
          </div>
          <Checkbox
            checked={hideIsolated}
            onChange={(e) => setHideIsolated(e.target.checked)}
            className="!ml-0 mt-2 text-xs"
          >
            <span className="text-[var(--color-text-2)]">{t('wiki.hideIsolated')}</span>
          </Checkbox>
        </div>
      )}

      {/* 洞察面板(右上):统计 + 最强关联 */}
      {showInsights && (
        <div className={`${panelCls} right-3 top-14 max-h-[calc(100%-120px)] w-[300px] overflow-auto p-3`}>
          <div className="mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-sm font-medium text-[var(--color-text-1)]">
              <BulbOutlined className="text-[var(--color-primary)]" /> {t('wiki.insights')}
            </span>
            <CloseOutlined
              className="cursor-pointer text-[var(--color-text-3)]"
              onClick={() => setShowInsights(false)}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: t('wiki.page'), value: ins.node_count ?? graph.nodes.length },
              { label: t('wiki.edges'), value: ins.edge_count ?? graph.edges.length },
              { label: t('wiki.community'), value: ins.community_count ?? legend.length },
              { label: t('wiki.largest'), value: ins.largest_community ?? 0 },
            ].map((s) => (
              <div key={s.label} className="rounded-md bg-[var(--color-fill-1)] px-2 py-1.5">
                <div className="text-xs text-[var(--color-text-3)]">{s.label}</div>
                <div className="text-lg font-semibold text-[var(--color-text-1)]">{s.value}</div>
              </div>
            ))}
          </div>
          <div className="mb-1 mt-3 text-xs font-medium text-[var(--color-text-2)]">{t('wiki.strongestRelations')}</div>
          {strongest.length ? (
            <ul className="space-y-1.5">
              {strongest.map((e, i) => (
                <li key={i} className="flex items-center justify-between gap-2 text-xs">
                  <span className="min-w-0 flex-1 truncate text-[var(--color-text-2)]">
                    {titleOf(e.from)} <span className="text-[var(--color-text-4)]">↔</span> {titleOf(e.to)}
                  </span>
                  <span className="shrink-0 rounded bg-[var(--color-fill-2)] px-1.5 text-[var(--color-text-3)]">
                    {e.weight ?? 1}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-xs text-[var(--color-text-3)]">--</div>
          )}
        </div>
      )}

      {/* 社区图例(左下) */}
      {showLegend && legend.length > 0 && (
        <div className={`${panelCls} bottom-3 left-3 max-w-[260px] p-3`}>
          <div className="mb-1.5 text-xs font-medium text-[var(--color-text-2)]">{t('wiki.communities')}</div>
          <ul className="space-y-1">
            {legend.map((l) => (
              <li key={l.community} className="flex items-center gap-2 text-xs">
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: communityColor(l.community) }}
                />
                <span className="min-w-0 flex-1 truncate text-[var(--color-text-2)]">{l.label}</span>
                <span className="shrink-0 text-[var(--color-text-3)]">{l.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default GraphExplorer;
