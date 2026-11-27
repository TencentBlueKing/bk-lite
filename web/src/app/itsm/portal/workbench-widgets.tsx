'use client';

import { AlertOutlined, AppstoreOutlined, ArrowRightOutlined, CheckCircleOutlined, ClockCircleOutlined, ClusterOutlined, FileAddOutlined, FileTextOutlined, StarFilled, StarOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Button, Empty, Pagination, TreeSelect } from 'antd';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import Link from 'next/link';
import { useEffect, useState, type MouseEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useItsmApi } from '../api/useItsmApi';
import { useTranslation } from '@/utils/i18n';
import type { PortalData, PortalService } from '../types';
import type { PortalDashboard, PortalTicket } from './workbench-types';

export function matchesServiceSearch(item: PortalService, search: string) {
  return `${item.name} ${item.description || ''} ${item.workflow_name || ''}`.toLowerCase().includes(search.trim().toLowerCase());
}

export const SERVICE_GRID_CLASS = 'grid grid-cols-[repeat(auto-fill,minmax(240px,280px))] gap-3';

function matchGlyph(label: string) {
  if (/问题/.test(label)) return { icon: <ClusterOutlined />, hue: 'var(--color-count)' };
  if (/事件/.test(label)) return { icon: <AlertOutlined />, hue: 'var(--color-warning)' };
  if (/请求|申请/.test(label)) return { icon: <FileAddOutlined />, hue: 'var(--color-primary)' };
  return null;
}

function resolveGlyph(portal: PortalData, item: PortalService) {
  const own = matchGlyph(item.name);
  if (own) return own;
  let current = item.catalog_id;
  const seen = new Set<number>();
  while (current && !seen.has(current)) {
    seen.add(current);
    const catalog = portal.catalogs.find(entry => entry.id === current);
    if (!catalog) break;
    const glyph = matchGlyph(catalog.name);
    if (glyph) return glyph;
    current = catalog.parent_id;
  }
  return { icon: <AppstoreOutlined />, hue: 'var(--color-text-2)' };
}

function ServiceGlyph({ portal, item, large = false, unified = false }: { portal: PortalData; item: PortalService; large?: boolean; unified?: boolean }) {
  const glyph = resolveGlyph(portal, item);
  if (unified) return <span aria-hidden className="portal-glyph portal-service-glyph">{glyph.icon}</span>;
  return <span aria-hidden className={`flex shrink-0 items-center justify-center ${large ? 'size-8 rounded-lg text-base' : 'size-6 rounded-md text-[13px]'}`} style={{ color: glyph.hue, background: glyph.hue.includes('warning') ? '#FFF4DE' : glyph.hue.includes('primary') ? '#EAF0FF' : glyph.hue.includes('count') ? '#D1FAF4' : '#F4F6FC' }}>{glyph.icon}</span>;
}

function statusHue(status: string) {
  if (/(?<!未)(完成|关闭|解决)/.test(status)) return 'var(--color-success)';
  if (/终止|失败|拒绝|驳回/.test(status)) return 'var(--color-fail)';
  if (/挂起|暂停/.test(status)) return 'var(--color-text-2)';
  if (/处理|进行|审批/.test(status)) return 'var(--color-warning)';
  if (/新|草稿/.test(status)) return 'var(--color-primary)';
  if (/撤回|取消/.test(status)) return 'var(--color-text-3)';
  return 'var(--color-text-2)';
}

function StatusPill({ status }: { status: string }) {
  const hue = statusHue(status);
  const tone = hue.includes('success') ? { key: 'success', ink: '#16A36A', wash: '#E5F5ED' }
    : hue.includes('warning') ? { key: 'warning', ink: '#E69500', wash: '#FFF4DE' }
    : hue.includes('primary') ? { key: 'primary', ink: '#2563EB', wash: '#EAF0FF' }
    : hue.includes('fail') ? { key: 'fail', ink: '#C2410C', wash: '#FFF1EB' }
    : { key: 'neutral', ink: '#64748B', wash: '#F4F6FC' };
  return <span className="portal-pill" data-tone={tone.key} style={{ color: tone.ink, background: tone.wash }}>{status}</span>;
}

interface ServiceActions {
  portal: PortalData;
  onFavorite: (id: number) => void;
  pending?: number;
  fromTicketCenter?: boolean;
  onNavigate?: () => void;
}

function favoriteBtn(t: ReturnType<typeof useTranslation>['t'], favorites: Set<number>, item: PortalService, onFavorite: (id: number) => void, pending?: number) {
  return <Button type="text" size="small" className="portal-fav shrink-0" aria-label={t(favorites.has(item.id) ? 'itsm.serviceBrowser.unfavoriteService' : 'itsm.serviceBrowser.favoriteService', undefined, { name: item.name })} title={t(favorites.has(item.id) ? 'itsm.serviceBrowser.unfavorite' : 'itsm.portal.favorite')} loading={pending === item.id} disabled={pending !== undefined} icon={favorites.has(item.id) ? <StarFilled className="portal-fav-on" /> : <StarOutlined className="portal-fav-off" />} onClick={() => onFavorite(item.id)} />;
}

export function ServiceListRows({ items, portal, onFavorite, pending, fromTicketCenter, onNavigate, variant, empty }: ServiceActions & { variant: 'action' | 'browse' | 'memory'; items: PortalService[]; empty?: string }) {
  const { t } = useTranslation();
  const favorites = new Set(portal.favorites.map(item => item.id));
  if (!items.length) {
    const fallback = variant === 'action' ? t('itsm.quickSubmit.emptyHots') : variant === 'memory' ? t('itsm.quickSubmit.emptyRecents') : t('itsm.serviceBrowser.emptyCards');
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty ?? fallback} />;
  }
  return <ul className="m-0 flex list-none flex-col p-0">{items.map(item => <li key={item.id} className={`portal-row flex gap-3 ${variant === 'memory' ? 'portal-row-memory' : ''} ${variant === 'browse' ? 'items-start' : 'items-center'}`}>
    <ServiceGlyph portal={portal} item={item} unified />
    <div className="min-w-0 flex-1">
      {portal.can_apply ? <Link href={`/itsm/tickets/new?service_id=${item.id}${fromTicketCenter ? '&from=tickets' : ''}`} onNavigate={onNavigate} className="block min-w-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"><EllipsisWithTooltip text={item.name} className="portal-name truncate" /></Link> : <EllipsisWithTooltip text={item.name} className="portal-name truncate" />}
      {variant === 'browse' ? <p className="portal-desc mb-0 mt-1 truncate">{item.description || item.workflow_name || t('itsm.serviceBrowser.description')}</p> : null}
    </div>
    {favoriteBtn(t, favorites, item, onFavorite, pending)}
  </li>)}</ul>;
}

export function ServiceTiles({ items, portal, onFavorite, pending, fromTicketCenter, onNavigate, empty }: ServiceActions & { items: PortalService[]; empty?: string }) {
  const { t } = useTranslation();
  if (!items.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty ?? t('itsm.quickSubmit.emptyHots')} />;
  return <QuickEntries items={items} portal={portal} onFavorite={onFavorite} pending={pending} fromTicketCenter={fromTicketCenter} onNavigate={onNavigate} />;
}

export function QuickEntries({ items, portal, onFavorite, pending, fromTicketCenter, onNavigate }: ServiceActions & { items: PortalService[] }) {
  const { t } = useTranslation();
  const favorites = new Set(portal.favorites.map(item => item.id));
  if (!items.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('itsm.quickSubmit.emptyHots')} />;
  return <div className="portal-quick-grid">{items.map(item => {
    const hint = item.description || item.workflow_name || t('itsm.serviceBrowser.description');
    const text = <>
      <EllipsisWithTooltip text={item.name} className="portal-name truncate" />
      <EllipsisWithTooltip text={hint} className="portal-desc mt-1 truncate" />
    </>;
    return <div key={item.id} className="portal-tile portal-quick">
      <ServiceGlyph portal={portal} item={item} unified />
      {portal.can_apply
        ? <Link href={`/itsm/tickets/new?service_id=${item.id}${fromTicketCenter ? '&from=tickets' : ''}`} onNavigate={onNavigate} className="portal-quick-copy block min-w-0 flex-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]">{text}</Link>
        : <span className="block min-w-0 flex-1">{text}</span>}
      {favoriteBtn(t, favorites, item, onFavorite, pending)}
    </div>;
  })}</div>;
}

export function ServiceCards({ items, portal, onFavorite, pending, fromTicketCenter, onNavigate, paginate = false }: ServiceActions & { paginate?: boolean; items: PortalService[] }) {
  const { t } = useTranslation();
  const favorites = new Set(portal.favorites.map(item => item.id));
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const current = Math.min(page, Math.max(1, Math.ceil(items.length / pageSize)));
  if (!items.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('itsm.serviceBrowser.emptyCards')} />;
  return <><div className={SERVICE_GRID_CLASS}>
    {(paginate ? items.slice((current - 1) * pageSize, current * pageSize) : items).map(item => <div key={item.id} className="group flex gap-3 rounded-md bg-[var(--color-fill-1)]/35 p-3 transition-colors hover:bg-[var(--color-fill-2)]">
      <ServiceGlyph portal={portal} item={item} large />
      <div className="min-w-0 flex-1">
        {portal.can_apply ? <Link href={`/itsm/tickets/new?service_id=${item.id}${fromTicketCenter ? '&from=tickets' : ''}`} onNavigate={onNavigate} className="font-medium text-[var(--color-text-1)] hover:text-[var(--color-primary)] focus-visible:text-[var(--color-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]">{item.name}<ArrowRightOutlined aria-hidden className="ml-2 text-xs opacity-0 group-hover:opacity-100" /></Link> : <span className="font-medium text-[var(--color-text-1)]">{item.name}</span>}
        <p className="mb-0 mt-1 line-clamp-2 text-xs leading-5 text-[var(--color-text-2)]">{item.description || item.workflow_name || t('itsm.serviceBrowser.description')}</p>
      </div>
      {favoriteBtn(t, favorites, item, onFavorite, pending)}
    </div>)}
  </div>{paginate && items.length > 10 && <Pagination className="mt-4 flex justify-end" current={current} pageSize={pageSize} total={items.length} showSizeChanger pageSizeOptions={[10, 20, 50, 100]} onChange={(next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size); }} />}</>;
}

const skeletonBar = 'animate-neutral-pulse motion-reduce:animate-none rounded-md bg-[var(--color-fill-2)]';

function DirectorySkeleton({ tiles, label }: { tiles: boolean; label: string }) {
  const tilesBody = <>
    <div className={`mb-3 h-3 w-16 ${skeletonBar}`} />
    <div className="portal-quick-grid">{Array.from({ length: 6 }, (_, index) => <div key={index} className="portal-tile portal-quick">
      <div className={`size-9 shrink-0 rounded-lg ${skeletonBar}`} />
      <div className="min-w-0 flex-1 space-y-2">
        <div className={`h-4 w-2/3 ${skeletonBar}`} />
        <div className={`h-3 w-4/5 ${skeletonBar}`} />
      </div>
    </div>)}</div>
  </>;
  const cardsBody = <div className={SERVICE_GRID_CLASS}>{Array.from({ length: 4 }, (_, index) => <div key={index} className="flex gap-3 rounded-md bg-[var(--color-fill-1)]/35 p-3">
    <div className={`size-10 shrink-0 ${skeletonBar}`} />
    <div className="min-w-0 flex-1 space-y-2">
      <div className={`h-4 w-3/4 ${skeletonBar}`} />
      <div className={`h-3 w-5/6 ${skeletonBar}`} />
    </div>
  </div>)}</div>;
  return <div role="status" aria-busy="true" aria-label={label}><div aria-hidden="true">{tiles ? tilesBody : cardsBody}</div></div>;
}

function CatalogFilter({ portal, value, onChange }: { portal: PortalData; value?: number; onChange: (value?: number) => void }) {
  const { t } = useTranslation();
  return <TreeSelect aria-label={t('itsm.serviceBrowser.filter')} className="portal-catalog-filter w-48" popupClassName="portal-catalog-dropdown" virtual={false} allowClear showSearch treeNodeFilterProp="title" treeDataSimpleMode placeholder={t('itsm.serviceBrowser.allCatalogs')} value={value} onChange={next => onChange(typeof next === 'number' ? next : undefined)} treeData={[{ id: 0, pId: null, value: 0, title: t('itsm.serviceBrowser.uncategorized') }, ...portal.catalogs.map(item => ({ id: item.id, pId: item.parent_id, value: item.id, title: item.name }))]} />;
}

export function ServiceBrowser({ portal, search, onFavorite, pending, fromTicketCenter, onNavigate, filterSlot = null, promptSlot = null, hideInlineFilter = false, compact = false, tiles = false }: ServiceActions & { search: string; filterSlot?: HTMLElement | null; promptSlot?: HTMLElement | null; hideInlineFilter?: boolean; compact?: boolean; tiles?: boolean }) {
  const { t } = useTranslation();
  const [catalog, setCatalog] = useState<number | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const { directoryPage } = useItsmApi();
  const [remote, setRemote] = useState<{items: PortalService[]; total: number; page: number; query: string}>();
  const [failure, setFailure] = useState('');
  const [attempt, setAttempt] = useState(0);
  const query = JSON.stringify({ keyword: search.trim(), page: String(page), page_size: String(pageSize), ...(catalog === undefined ? {} : { catalog: String(catalog) }) });
  const needsQuery = portal.service_total !== undefined && (page !== 1 || pageSize !== 10 || !!search.trim() || catalog !== undefined);
  useEffect(() => {
    setFailure('');
    if (!needsQuery) return;
    let active = true;
    const timer = setTimeout(() => {
      void directoryPage(JSON.parse(query)).then(value => {
        if (active) setRemote({...value, query});
      }).catch(() => { if (active) setFailure('目录加载失败'); });
    }, 150);
    return () => { active = false; clearTimeout(timer); };
  }, [needsQuery, query, directoryPage, attempt]);
  const selected = new Set<number>(catalog === undefined ? [] : [catalog]);
  for (let i = 0; i < portal.catalogs.length; i++) {
    let added = false;
    portal.catalogs.forEach(item => { if (item.parent_id !== null && selected.has(item.parent_id) && !selected.has(item.id)) { selected.add(item.id); added = true; } });
    if (!added) break;
  }
  const filtered = portal.services.filter(item => (catalog === undefined || (catalog === 0 ? !item.catalog_id : selected.has(item.catalog_id || 0))) && matchesServiceSearch(item, search));
  const result = remote?.query === query ? remote : undefined;
  const total = needsQuery ? result?.total ?? 0 : portal.service_total ?? filtered.length;
  const current = needsQuery ? result?.page ?? page : Math.min(page, Math.max(1, Math.ceil(total / pageSize)));
  const shown = needsQuery ? result?.items ?? [] : filtered.slice((current - 1) * pageSize, current * pageSize);
  const groups = [...new Set(shown.map(item => item.catalog_id))];
  const filter = <CatalogFilter portal={portal} value={catalog} onChange={value => { setCatalog(value); setPage(1); }} />;
  const placedFilter: ReactNode = filterSlot ? createPortal(filter, filterSlot) : hideInlineFilter ? null : filter;
  const listProps = { portal, onFavorite, pending, fromTicketCenter, onNavigate };
  return <div className="portal-directory">
    {tiles && shown.length && promptSlot ? createPortal(<p className="portal-head-note portal-desc mb-0 text-xs text-[var(--color-text-2)]">{t('itsm.serviceBrowser.prompt')}</p>, promptSlot) : null}
    {tiles ? placedFilter : <div className={hideInlineFilter ? 'mb-3' : 'mb-3 flex items-center justify-between gap-3'}>
      <span className="portal-desc text-xs text-[var(--color-text-2)]">{t('itsm.serviceBrowser.prompt')}</span>
      {placedFilter}
    </div>}
    <div className="portal-directory-list">
      {failure ? <Button onClick={() => setAttempt(value => value + 1)}>{failure}，重试</Button> : needsQuery && !result ? <DirectorySkeleton tiles={tiles} label={t('itsm.quickSubmit.loading')} /> : !shown.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={search ? t('itsm.serviceBrowser.noMatch') : t('itsm.serviceBrowser.empty')} /> : groups.map(id => <section key={id || 0} className="mb-4 last:mb-0">
        <h3 className="portal-desc mb-3 text-xs font-medium text-[var(--color-text-2)]">{portal.catalogs.find(item => item.id === id)?.name || t('itsm.serviceBrowser.fallbackCatalog')}</h3>
        {tiles ? <ServiceTiles {...listProps} items={shown.filter(item => item.catalog_id === id)} /> : compact ? <ServiceListRows {...listProps} items={shown.filter(item => item.catalog_id === id)} variant="browse" /> : <ServiceCards items={shown.filter(item => item.catalog_id === id)} {...listProps} />}
      </section>)}
    </div>
    {total > 10 && <Pagination className="portal-directory-pager mt-4 flex justify-end" size="small" current={current} pageSize={pageSize} total={total} showSizeChanger pageSizeOptions={[10, 20, 50, 100]} onChange={(next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size); }} />}
  </div>;
}

export function PortalStatsGrid({ stats, half }: { stats: PortalDashboard['stats']; half?: boolean }) {
  const cells = [
    { key: 'total', label: '可见工单', value: stats.total, icon: <FileTextOutlined />, ink: '#17243C', wash: '#EAF0FF' },
    { key: 'todo', label: '我的待办', value: stats.todo, icon: <ClockCircleOutlined />, ink: '#E69500', wash: '#FFF4DE' },
    { key: 'active', label: '进行中', value: stats.active, icon: <ThunderboltOutlined />, ink: '#2563EB', wash: '#EAF0FF' },
    { key: 'finished', label: '已完成', value: stats.finished, icon: <CheckCircleOutlined />, ink: '#16A36A', wash: '#E5F5ED' },
  ];
  return <div aria-label="工单统计" className={`grid gap-4 ${half ? 'grid-cols-2' : 'grid-cols-2 md:grid-cols-4'}`}>{cells.map(cell => <div key={cell.key} data-tone={cell.key} className="portal-card portal-stat flex min-h-[92px] min-w-0 cursor-default items-center gap-3 px-4">
    <span aria-hidden className="portal-glyph portal-stat-glyph" style={{ color: cell.ink, background: cell.wash }}>{cell.icon}</span>
    <div className="min-w-0">
      <div className="portal-stat-label truncate">{cell.label}</div>
      <div className="portal-stat-value tabular-nums" style={{ color: cell.ink }}>{cell.value}</div>
    </div>
  </div>)}</div>;
}

export function TicketRows({ items, allowed }: { items: PortalTicket[]; allowed?: boolean }) {
  if (!items.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={allowed === false ? '暂无工单查看权限' : '暂无工单'} />;
  return <div className="flex min-w-0 flex-col">{items.map(item => <Link key={item.id} href={`/itsm/tickets/${item.id}`} className="portal-row group flex min-w-0 items-center gap-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]">
    <span className="min-w-0 flex-1">
      <EllipsisWithTooltip text={item.title} className="portal-name truncate group-hover:text-[var(--color-primary)]" />
      <span className="portal-meta mt-1 block tabular-nums">{item.sn}</span>
    </span>
    <StatusPill status={item.status} />
  </Link>)}</div>;
}

function trendLabels(length: number) {
  const picked = Array.from({ length }, (_, index) => index).filter(index => index === 0 || index === length - 1 || index % 3 === 0);
  return picked.filter((index, position) => position === picked.length - 1 || picked[position + 1] - index > 1);
}

export function TrendChart({ data }: { data: PortalDashboard['trend'] }) {
  const [tip, setTip] = useState<{ index: number; x: number; y: number; width: number; height: number }>();
  const hasActivity = data.some(item => item.created > 0 || item.finished > 0);
  const caption = <p className="portal-meta mb-0 mt-2 shrink-0">完成量按记录的完成时间统计；历史工单未记录完成时间的不计入趋势。</p>;
  if (!hasActivity) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="近 14 天没有新建或完成的工单" />;
  const max = Math.max(...data.flatMap(item => [item.created, item.finished]));
  const yTicks = [max, Math.round(max / 2), 0].filter((tick, index, all) => all.indexOf(tick) === index);
  const span = Math.max(data.length - 1, 1);
  const xPct = (index: number) => (index / span) * 100;
  const xOf = (index: number) => (index / span) * 500;
  const yOf = (value: number) => 6 + 92 * (1 - value / max);
  const line = (key: 'created' | 'finished') => data.map((item, index) => `${xOf(index)},${yOf(item[key])}`).join(' ');
  const labels = new Set(trendLabels(data.length));
  const track = (event: MouseEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - box.left;
    const y = event.clientY - box.top;
    const index = Math.round(Math.min(1, Math.max(0, x / Math.max(box.width, 1))) * span);
    setTip({ index, x, y, width: box.width, height: box.height });
  };
  const hovered = tip ? data[tip.index] : undefined;
  const tipShift = !tip ? undefined : `translate(${tip.x > tip.width - 132 ? 'calc(-100% - 12px)' : '12px'}, ${tip.y < 64 ? '12px' : 'calc(-100% - 12px)'})`;
  return <div className="flex h-full min-h-0 w-full flex-1 flex-col">
    <div className="portal-meta mb-2 flex shrink-0 items-center justify-between gap-3">
      <div className="flex items-center gap-4">
        <span className="inline-flex items-center gap-1.5"><span className="h-px w-4 border-t-2 border-[var(--color-primary)]" />新建</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-px w-4 border-t-2 border-dashed border-[var(--color-success)]" />完成</span>
      </div>
      <p className="mb-0 tabular-nums">近 14 天</p>
    </div>
    <div className="flex min-h-[168px] w-full flex-1 gap-2">
      <div className="relative h-full w-8 shrink-0">{yTicks.map(tick => <span key={tick} className="portal-meta absolute right-0 -translate-y-1/2 tabular-nums" style={{ top: `${yOf(tick)}%` }}>{tick}</span>)}</div>
      <div className="relative min-h-0 min-w-0 flex-1" onMouseMove={track} onMouseLeave={() => setTip(undefined)}>
          <svg viewBox="0 0 500 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" role="img" aria-label="近十四天新建与完成工单趋势">
            {yTicks.map(tick => <line key={tick} x1="0" y1={yOf(tick)} x2="500" y2={yOf(tick)} stroke="var(--color-border-2)" strokeOpacity="0.6" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />)}
            <polygon points={`${xOf(0)},${yOf(0)} ${line('created')} ${xOf(data.length - 1)},${yOf(0)}`} fill="var(--color-primary)" fillOpacity="0.08" />
            <polyline points={line('created')} fill="none" stroke="var(--color-primary)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            <polyline points={line('finished')} fill="none" stroke="var(--color-success)" strokeWidth="1.5" strokeDasharray="4 3" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          </svg>
          {data.map((item, index) => <button key={item.date} type="button" className={`pointer-events-none absolute inset-y-0 w-8 border-0 bg-transparent p-0 focus-visible:pointer-events-auto focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)] ${index === 0 ? 'left-0' : index === data.length - 1 ? 'right-0' : '-translate-x-1/2'}`} style={index === 0 || index === data.length - 1 ? undefined : { left: `${xPct(index)}%` }} aria-label={`${item.date}：新建 ${item.created}，完成 ${item.finished}`} onFocus={event => { const box = event.currentTarget.parentElement?.getBoundingClientRect(); if (!box) return; setTip({ index, x: (xPct(index) / 100) * box.width, y: box.height * 0.35, width: box.width, height: box.height }); }} onBlur={() => setTip(undefined)}>
            <span className={`pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-[var(--color-border-1)] ${tip?.index === index ? 'opacity-100' : 'opacity-0'}`} />
            <span className={`pointer-events-none absolute left-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--color-primary)] ${tip?.index === index ? 'opacity-100' : 'opacity-0'}`} style={{ top: `${yOf(item.created)}%` }} />
            <span className={`pointer-events-none absolute left-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--color-success)] ${tip?.index === index ? 'opacity-100' : 'opacity-0'}`} style={{ top: `${yOf(item.finished)}%` }} />
          </button>)}
          {hovered && tip ? <div className="portal-trend-tip" role="tooltip" style={{ left: tip.x, top: tip.y, transform: tipShift }}><strong className="tabular-nums">{hovered.date.slice(5)}</strong><span>新建 {hovered.created}</span><span>完成 {hovered.finished}</span></div> : null}
      </div>
    </div>
    <div className="portal-meta relative ml-10 mt-2 h-4 overflow-hidden tabular-nums">
      {data.map((item, index) => labels.has(index) ? <span key={item.date} className={`absolute top-0 whitespace-nowrap ${index === data.length - 1 ? 'right-0' : index === 0 ? 'left-0' : '-translate-x-1/2'}`} style={index === 0 || index === data.length - 1 ? undefined : { left: `${xPct(index)}%` }}>{item.date.slice(5)}</span> : null)}
    </div>
    {caption}
  </div>;
}