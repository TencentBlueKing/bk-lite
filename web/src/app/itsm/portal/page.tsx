'use client';

import { AppstoreOutlined, ArrowDownOutlined, ArrowUpOutlined, BellOutlined, CaretRightOutlined, CheckCircleOutlined, ClockCircleOutlined, DeleteOutlined, EditOutlined, FileTextOutlined, HolderOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, SettingOutlined, StarOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Alert, App, Button, Empty, Input, Select, Tooltip } from 'antd';
import Link from 'next/link';
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import { defaultBasicSettings, useItsmRuntimeSettings } from '../settings/runtime-settings';
import type { PortalData } from '../types';
import { widgetNames } from './workbench-types';
import type { PortalDashboard, PortalLayout, WidgetType } from './workbench-types';
import { useTranslation } from '@/utils/i18n';
import { PortalStatsGrid, QuickEntries, ServiceBrowser, ServiceListRows, TicketRows, TrendChart } from './workbench-widgets';
import './portal.css';

const pulse = 'animate-neutral-pulse motion-reduce:animate-none rounded-md bg-[var(--color-fill-1)]';
const titleIcons: Record<WidgetType, ReactNode> = { stats: <AppstoreOutlined />, services: <AppstoreOutlined />, todo: <ClockCircleOutlined />, tickets: <FileTextOutlined />, trend: <CheckCircleOutlined />, announcements: <BellOutlined />, quick: <ThunderboltOutlined />, recents: <ClockCircleOutlined />, favorites: <StarOutlined /> };

function PortalSkeleton() {
  return <div role="status" aria-busy="true" aria-label="门户加载中…" className="itsm-portal is-plain flex flex-col gap-4">
    <div aria-hidden="true" className="portal-hero">
      <div className={`h-8 w-40 ${pulse}`} />
      <div className={`mt-3 h-4 w-72 ${pulse}`} />
      <div className={`mt-5 h-11 w-[58%] max-w-[720px] ${pulse}`} />
    </div>
    <div aria-hidden="true" className="grid grid-cols-2 gap-4 md:grid-cols-4">{Array.from({ length: 4 }, (_, index) => <div key={index} className={`portal-card h-[92px] ${pulse}`} />)}</div>
    <div aria-hidden="true" className="grid grid-cols-12 gap-4">
      <div className={`portal-card col-span-12 h-36 lg:col-span-6 ${pulse}`} />
      <div className={`portal-card col-span-12 h-36 lg:col-span-6 ${pulse}`} />
    </div>
  </div>;
}

export default function PortalPage() {
  const api = useItsmApi();
  const { settings } = useItsmRuntimeSettings();
  const { t } = useTranslation();
  const { message } = App.useApp();
  const fail = (error: unknown) => message.error(error instanceof Error ? error.message : '操作失败，请重试');
  const [portal, setPortal] = useState<PortalData>();
  const [layout, setLayout] = useState<PortalLayout>();
  const [dashboard, setDashboard] = useState<PortalDashboard>();
  const [draft, setDraft] = useState<PortalLayout>();
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [favoriteBusy, setFavoriteBusy] = useState<number>();
  const [dragged, setDragged] = useState<number>();
  const [dropIndex, setDropIndex] = useState<number>();
  const [serviceFilterSlot, setServiceFilterSlot] = useState<HTMLDivElement | null>(null);
  const [servicePromptSlot, setServicePromptSlot] = useState<HTMLDivElement | null>(null);
  const load = useCallback(async () => {
    setError('');
    try {
      const [p, l, d] = await Promise.all([api.portal(), api.portalLayout(), api.portalDashboard()]);
      setPortal(p as PortalData); setLayout(l as PortalLayout); setDashboard(d as PortalDashboard);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '门户加载失败'); }
  }, [api.portal, api.portalLayout, api.portalDashboard]);
  useEffect(() => { if (api.ready) void load(); }, [api.ready, load]);
  const favorite = async (id: number) => {
    if (favoriteBusy !== undefined) return;
    setFavoriteBusy(id);
    try { await api.toggleFavorite(id); setPortal(await api.portal() as PortalData); } catch (reason) { fail(reason); } finally { setFavoriteBusy(undefined); }
  };
  const save = async () => {
    if (!draft?.title.trim()) { message.warning('请填写门户标题'); return; }
    setBusy(true);
    try { setLayout(await api.savePortalLayout(draft) as PortalLayout); setDraft(undefined); message.success('门户布局已发布'); } catch (reason) { fail(reason); } finally { setBusy(false); }
  };
  const move = (from: number, to: number) => {
    if (!draft || to < 0 || to >= draft.widgets.length) return;
    const widgets = [...draft.widgets]; const [item] = widgets.splice(from, 1); widgets.splice(to, 0, item); setDraft({ ...draft, widgets });
  };
  const upload = (file?: File) => {
    if (!file || !draft) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 1024 * 1024) { message.warning('请选择 1 MB 以内的 PNG、JPEG 或 WebP 图片'); return; }
    const reader = new FileReader();
    reader.onload = () => setDraft(value => value ? { ...value, background: String(reader.result) } : value);
    reader.onerror = () => message.error('图片读取失败');
    reader.readAsDataURL(file);
  };
  const gridRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const grid = gridRef.current;
    if (!grid) return;
    let frame = 0;
    let width = -1;
    const naturalHeight = (card: HTMLElement) => {
      const header = card.querySelector<HTMLElement>(':scope > .portal-head');
      const body = card.querySelector<HTMLElement>(':scope > .portal-body');
      if (!header || !body) return card.offsetHeight;
      const style = getComputedStyle(card);
      const border = (parseFloat(style.borderTopWidth) || 0) + (parseFloat(style.borderBottomWidth) || 0);
      return header.offsetHeight + body.scrollHeight + (parseFloat(style.paddingTop) || 0) + (parseFloat(style.paddingBottom) || 0) + (parseFloat(style.rowGap || style.gap) || 0) + border;
    };
    const fit = () => {
      if (grid.clientWidth === 0) return;
      const cards = [...grid.querySelectorAll<HTMLElement>(':scope > section.portal-card')];
      cards.forEach(card => { card.style.height = 'auto'; card.style.maxHeight = ''; });
      const groups = new Map<number, HTMLElement[]>();
      cards.forEach(card => {
        const top = Math.round(card.offsetTop);
        const list = groups.get(top) ?? [];
        list.push(card);
        groups.set(top, list);
      });
      groups.forEach(list => {
        const specs = list.map(card => {
          const style = getComputedStyle(card);
          const max = Number.parseFloat(style.maxHeight);
          const min = Number.parseFloat(style.minHeight);
          return { card, max: Number.isFinite(max) ? max : Number.POSITIVE_INFINITY, min: Number.isFinite(min) ? min : 0, natural: naturalHeight(card) };
        });
        const row = Math.max(...specs.map(item => Math.min(Math.max(item.natural, item.min), item.max)));
        const height = `${Math.round(row)}px`;
        specs.forEach(item => { item.card.style.maxHeight = height; item.card.style.height = height; });
      });
      width = grid.clientWidth;
    };
    const schedule = () => {
      if (grid.clientWidth === width) return;
      width = grid.clientWidth;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(fit);
    };
    schedule();
    if (typeof ResizeObserver === 'undefined') return () => cancelAnimationFrame(frame);
    const observer = new ResizeObserver(schedule);
    observer.observe(grid);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      grid.querySelectorAll<HTMLElement>(':scope > section.portal-card').forEach(card => { card.style.height = ''; card.style.maxHeight = ''; });
    };
  }, [draft, portal, dashboard, search]);
  if (error) return <div className="itsm-portal is-plain"><Alert type="error" message={error} action={<Button onClick={() => void load()}>重试</Button>} /></div>;
  if (!portal || !layout || !dashboard) return <PortalSkeleton />;
  const current = draft || layout;
  const isImage = current.background.startsWith('data:image/');
  const canvas = isImage ? 'is-image' : current.background === 'blue' || current.background === 'violet' || current.background === 'mint' ? `is-${current.background}` : 'is-plain';
  const rowLimit = 'max-h-[380px]';
  const widget = (type: WidgetType, half: boolean) => {
    switch (type) {
      case 'services': return <ServiceBrowser portal={portal} search={search} onFavorite={favorite} pending={favoriteBusy} filterSlot={serviceFilterSlot} promptSlot={servicePromptSlot} hideInlineFilter compact={half} tiles />;
      case 'quick': return <QuickEntries portal={portal} items={(portal.hots.length ? portal.hots : portal.services).slice(0, 6)} onFavorite={favorite} pending={favoriteBusy} />;
      case 'recents': return <ServiceListRows variant="memory" empty={t('itsm.quickSubmit.emptyRecents')} portal={portal} items={portal.recents} onFavorite={favorite} pending={favoriteBusy} />;
      case 'favorites': return <ServiceListRows variant="memory" empty={t('itsm.quickSubmit.emptyFavorites')} portal={portal} items={portal.favorites} onFavorite={favorite} pending={favoriteBusy} />;
      case 'todo': case 'tickets': return <TicketRows items={dashboard[type]} allowed={dashboard.can_view_tickets} />;
      case 'trend': return <TrendChart data={dashboard.trend} />;
      case 'announcements': return dashboard.announcements.length ? <div className="portal-announce-list">{dashboard.announcements.map(item => <details key={item.id} className="portal-announce"><summary><CaretRightOutlined className="portal-announce-arrow" aria-hidden /><span className="portal-name truncate">{item.title}</span><time className="portal-meta shrink-0 tabular-nums">{item.created_at.slice(0, 10)}</time></summary><p className="portal-desc portal-announce-body mb-0 whitespace-pre-wrap break-words">{item.content}</p></details>)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无公告" />;
      case 'stats': return <PortalStatsGrid stats={dashboard.stats} half={half} />;
    }
  };
  // 搜索始终显示服务结果，不依赖管理员是否配置了目录组件。
  const visibleWidgets = search.trim() ? [{ type: 'services' as const, width: 12 as const }] : current.widgets;
  return <div className={`itsm-portal ${canvas} flex flex-col gap-4`} style={isImage ? { ['--portal-image' as string]: `url("${current.background}")` } : undefined}>
    <section className="portal-hero">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="portal-hero-kicker">{settings.product_name === defaultBasicSettings.product_name ? 'IT SERVICE PORTAL' : settings.product_name}</div>
          <h1 className="portal-hero-title text-pretty">{current.title}</h1>
          <p className="portal-hero-desc mb-0 mt-2 line-clamp-2">{current.subtitle}</p>
        </div>
        <div className="portal-hero-actions">
          {!draft && <Tooltip title="刷新门户"><Button aria-label="刷新门户" icon={<ReloadOutlined />} onClick={() => void load()} /></Tooltip>}
          {portal.can_manage && !draft && <><Link href="/itsm/portal/services"><Button icon={<SettingOutlined />}>管理服务</Button></Link><Button className="portal-hero-edit" icon={<EditOutlined />} onClick={() => { setSearch(''); setDraft(structuredClone(layout)); }}>编排门户</Button></>}
          {draft && <><Button disabled={busy} onClick={() => setDraft(undefined)}>取消编辑</Button><Button type="primary" loading={busy} onClick={() => void save()}>发布布局</Button></>}
        </div>
      </div>
      <Input aria-label="搜索服务" name="service-search" autoComplete="off" className="portal-search mt-4" prefix={<SearchOutlined />} placeholder="搜索服务名称、描述或流程" allowClear value={search} onChange={event => setSearch(event.target.value)} />
    </section>
    {draft && <section aria-label="门户配置" className="portal-card p-5">
      <p className="portal-desc mb-4">调整组件顺序和宽度，发布后对当前域用户生效。可拖动组件，或使用上下箭头排序。</p>
      <div className="grid gap-4 md:grid-cols-3">
        <label className="portal-desc flex flex-col gap-2">门户标题<Input aria-label="门户标题" maxLength={60} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
        <label className="portal-desc flex flex-col gap-2">欢迎文案<Input aria-label="欢迎文案" maxLength={160} value={draft.subtitle} onChange={event => setDraft({ ...draft, subtitle: event.target.value })} /></label>
        <div className="flex min-w-0 flex-col gap-2"><span className="portal-desc">背景</span><div className="flex gap-2"><Select aria-label="背景样式" className="min-w-0 flex-1" value={isImage ? 'custom' : draft.background} options={[{ value: '', label: '无背景' }, { value: 'blue', label: '晴空蓝' }, { value: 'violet', label: '浅紫' }, { value: 'mint', label: '薄荷' }, ...(isImage ? [{ value: 'custom', label: '自定义图片' }] : [])]} onChange={value => setDraft({ ...draft, background: value === 'custom' ? draft.background : value })} /><label className="portal-name flex shrink-0 cursor-pointer items-center rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-3 focus-within:ring-2 focus-within:ring-[var(--color-primary)]">上传图片<input aria-label="上传背景图" type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={event => { upload(event.target.files?.[0]); event.target.value = ''; }} /></label></div><span className="portal-meta">PNG / JPEG / WebP，最大 1 MB</span></div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">{(Object.keys(widgetNames) as WidgetType[]).filter(type => !draft.widgets.some(item => item.type === type)).map(type => <Button key={type} size="small" icon={<PlusOutlined />} onClick={() => setDraft({ ...draft, widgets: [...draft.widgets, { type, width: 6 }] })}>{widgetNames[type]}</Button>)}</div>
    </section>}
    <div ref={gridRef} className="grid grid-cols-12 items-stretch gap-4">
      {visibleWidgets.map((item, index) => {
        const half = item.width === 6;
        const limit = rowLimit;
        const name = widgetNames[item.type];
        const layoutOps = draft && !search.trim() ? <div className="portal-layout-ops"><Tooltip title={`拖动${name}`}><button type="button" aria-label={`拖动${name}`} draggable className="portal-layout-handle" onDragStart={event => { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', item.type); setDragged(index); }} onDragEnd={() => { setDragged(undefined); setDropIndex(undefined); }}><HolderOutlined aria-hidden /></button></Tooltip><div className="portal-layout-bar"><Select aria-label={`${name}宽度`} size="small" className="portal-layout-width" popupMatchSelectWidth={false} value={item.width} options={[{ value: 6, label: '半宽' }, { value: 12, label: '整行' }]} onChange={width => { const next = Number(width) === 12 ? 12 : 6; setDraft({ ...draft, widgets: draft.widgets.map((w, i) => i === index ? { ...w, width: next } : w) }); }} /><span className="portal-layout-rule" aria-hidden /><Tooltip title={`上移${name}`}><span className="inline-flex"><Button type="text" aria-label={`上移${name}`} disabled={index === 0} icon={<ArrowUpOutlined />} onClick={() => move(index, index - 1)} /></span></Tooltip><Tooltip title={`下移${name}`}><span className="inline-flex"><Button type="text" aria-label={`下移${name}`} disabled={index === draft.widgets.length - 1} icon={<ArrowDownOutlined />} onClick={() => move(index, index + 1)} /></span></Tooltip><Tooltip title={`移除${name}`}><span className="inline-flex"><Button type="text" className="is-remove" aria-label={`移除${name}`} icon={<DeleteOutlined />} onClick={() => setDraft({ ...draft, widgets: draft.widgets.filter((_, i) => i !== index) })} /></span></Tooltip></div></div> : null;
        const dropMark = dropIndex === index && dragged !== index ? 'outline outline-2 outline-[var(--color-primary)]' : '';
        if (item.type === 'stats') return <section key={item.type} onDragOver={event => { if (draft && dragged !== undefined) { event.preventDefault(); setDropIndex(index); } }} onDrop={event => { event.preventDefault(); if (dragged !== undefined) move(dragged, index); setDragged(undefined); setDropIndex(undefined); }} className={`col-span-12 min-w-0 ${half ? 'lg:col-span-6' : ''} ${dropMark}`}>
          {draft ? <div className="mb-2 flex h-8 items-center justify-end">{layoutOps}</div> : null}
          {widget(item.type, half)}
        </section>;
        return <section key={item.type} onDragOver={event => { if (draft && dragged !== undefined) { event.preventDefault(); setDropIndex(index); } }} onDrop={event => { event.preventDefault(); if (dragged !== undefined) move(dragged, index); setDragged(undefined); setDropIndex(undefined); }} className={`portal-card col-span-12 flex min-h-0 min-w-0 flex-col gap-3 overflow-hidden p-4 ${limit} ${half ? 'lg:col-span-6' : ''} ${draft ? 'is-draft' : ''} ${dropMark}`}>
          <div className={`portal-head flex shrink-0 justify-between gap-3 ${item.type === 'services' ? 'min-h-8 items-start' : 'h-8 items-center'}`}>
            {item.type === 'services' ? <div className="portal-head-copy min-w-0">
              <span className="portal-title-icon" aria-hidden>{titleIcons[item.type]}</span>
              <h2 className="portal-card-title min-w-0 truncate">{widgetNames[item.type]}</h2>
              <div ref={setServicePromptSlot} className="portal-head-slot" />
            </div> : <h2 className="portal-card-title flex min-w-0 items-center"><span className="portal-title-icon" aria-hidden>{titleIcons[item.type]}</span><span className="truncate">{widgetNames[item.type]}</span></h2>}
            <div className="flex shrink-0 items-center gap-1">
              {item.type === 'services' ? <div ref={setServiceFilterSlot} /> : null}
              {layoutOps ?? ((item.type === 'todo' || item.type === 'tickets') && dashboard.can_view_tickets ? <Link className="portal-link inline-flex items-center focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]" href={item.type === 'todo' ? '/itsm/tickets?tab=mine' : '/itsm/tickets'}>查看全部</Link> : null)}
            </div>
          </div>
          <div className="portal-body flex min-h-0 flex-1 flex-col">{widget(item.type, half)}</div>
        </section>;
      })}
    </div>
    {!visibleWidgets.length && <Empty description="暂无工作台组件" />}
  </div>;
}
