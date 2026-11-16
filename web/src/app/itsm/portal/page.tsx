'use client';

import { AppstoreOutlined, ArrowDownOutlined, ArrowUpOutlined, BellOutlined, CheckCircleOutlined, ClockCircleOutlined, DeleteOutlined, EditOutlined, FileTextOutlined, HolderOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, SettingOutlined, StarOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Alert, App, Button, Empty, Input, Select, Skeleton, Tooltip } from 'antd';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import type { PortalData } from '../types';
import { backgrounds, widgetNames } from './workbench-types';
import type { PortalDashboard, PortalLayout, WidgetType } from './workbench-types';
import { ServiceBrowser, ServiceCards, TicketRows, TrendChart } from './workbench-widgets';

const icons = { stats: <AppstoreOutlined />, services: <AppstoreOutlined />, todo: <ClockCircleOutlined />, tickets: <FileTextOutlined />, trend: <CheckCircleOutlined />, announcements: <BellOutlined />, quick: <ThunderboltOutlined />, recents: <ClockCircleOutlined />, favorites: <StarOutlined /> };

export default function PortalPage() {
  const api = useItsmApi();
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
  if (error) return <Alert type="error" message={error} action={<Button onClick={() => void load()}>重试</Button>} />;
  if (!portal || !layout || !dashboard) return <Skeleton active paragraph={{ rows: 10 }} />;
  const current = draft || layout;
  const isImage = current.background.startsWith('data:image/');
  const background = isImage ? `linear-gradient(90deg, rgba(245,249,255,.96), rgba(245,249,255,.75)), url("${current.background}")` : backgrounds[current.background];
  const widget = (type: WidgetType) => {
    switch (type) {
      case 'services': return <ServiceBrowser portal={portal} search={search} onFavorite={favorite} pending={favoriteBusy} />;
      case 'quick': case 'recents': case 'favorites': return <ServiceCards paginate portal={portal} items={type === 'quick' ? (portal.hots.length ? portal.hots : portal.services).slice(0, 6) : portal[type]} onFavorite={favorite} pending={favoriteBusy} />;
      case 'todo': case 'tickets': return <TicketRows items={dashboard[type]} allowed={dashboard.can_view_tickets} />;
      case 'trend': return <TrendChart data={dashboard.trend} />;
      case 'announcements': return dashboard.announcements.length ? <div className="space-y-3">{dashboard.announcements.map(item => <details key={item.id} className="rounded-lg bg-[var(--color-fill-1)] p-3"><summary className="cursor-pointer text-sm font-medium"><span>{item.title}</span><time className="ml-3 text-xs font-normal text-[var(--color-text-3)]">{item.created_at.slice(0, 10)}</time></summary><p className="mb-0 mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-[var(--color-text-2)]">{item.content}</p></details>)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无公告" />;
      case 'stats': return <div className="grid grid-cols-2 gap-4 md:grid-cols-4">{([
        ['total', '可见工单', <FileTextOutlined key="total" />, 'bg-blue-50 text-blue-600'], ['todo', '我的待办', <ClockCircleOutlined key="todo" />, 'bg-amber-50 text-amber-600'],
        ['active', '进行中', <ThunderboltOutlined key="active" />, 'bg-indigo-50 text-indigo-600'], ['finished', '已完成', <CheckCircleOutlined key="finished" />, 'bg-emerald-50 text-emerald-600'],
      ] as const).map(([key, label, icon, color]) => <div key={key} className="flex items-center gap-4 rounded-xl border border-[var(--color-border)] p-4"><span className={`flex h-11 w-11 items-center justify-center rounded-xl text-xl ${color}`}>{icon}</span><div><div className="text-xs text-[var(--color-text-3)]">{label}</div><div className="mt-1 text-2xl font-semibold tabular-nums">{dashboard.stats[key]}</div></div></div>)}</div>;
    }
  };
  // 搜索始终显示服务结果，不依赖管理员是否配置了目录组件。
  const visibleWidgets = search.trim() ? [{ type: 'services' as const, width: 12 as const }] : current.widgets;
  return <div className="flex flex-col gap-5 pb-6">
    <section className="relative overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)] px-6 py-7 md:px-8" style={{ backgroundImage: background, backgroundPosition: 'center', backgroundSize: 'cover' }}>
      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div><div className="mb-2 text-xs font-medium tracking-widest text-blue-600">IT SERVICE PORTAL</div><h1 className={`mb-2 text-2xl font-semibold ${current.background ? 'text-slate-800' : 'text-[var(--color-text-1)]'}`}>{current.title}</h1><p className={`mb-0 text-sm ${current.background ? 'text-slate-500' : 'text-[var(--color-text-3)]'}`}>{current.subtitle}</p></div>
        <div className="flex flex-wrap gap-2">
          {!draft && <Tooltip title="刷新门户"><Button aria-label="刷新门户" icon={<ReloadOutlined />} onClick={() => void load()} /></Tooltip>}
          {portal.can_manage && !draft && <><Link href="/itsm/portal/services"><Button icon={<SettingOutlined />}>管理服务</Button></Link><Button icon={<EditOutlined />} onClick={() => { setSearch(''); setDraft(structuredClone(layout)); }}>编排门户</Button></>}
          {draft && <><Button disabled={busy} onClick={() => setDraft(undefined)}>取消编辑</Button><Button type="primary" loading={busy} onClick={() => void save()}>发布布局</Button></>}
        </div>
      </div>
      <Input aria-label="搜索服务" size="large" className="mt-6 max-w-xl !rounded-xl" prefix={<SearchOutlined className="mr-2 text-blue-500" />} placeholder="搜索服务名称、描述或流程" allowClear value={search} onChange={event => setSearch(event.target.value)} />
    </section>
    {draft && <section aria-label="门户配置" className="rounded-xl border border-dashed border-blue-300 bg-[var(--color-bg)] p-5">
      <p className="mb-4 text-sm text-[var(--color-text-3)]">调整组件顺序和宽度，发布后对当前域用户生效。可拖动组件，或使用上下箭头排序。</p>
      <div className="grid gap-4 md:grid-cols-3">
        <label className="text-xs">门户标题<Input aria-label="门户标题" className="mt-2" maxLength={60} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
        <label className="text-xs">欢迎文案<Input aria-label="欢迎文案" className="mt-2" maxLength={160} value={draft.subtitle} onChange={event => setDraft({ ...draft, subtitle: event.target.value })} /></label>
        <div><span className="text-xs">背景</span><div className="mt-2 flex gap-2"><Select aria-label="背景样式" className="min-w-24 flex-1" value={isImage ? 'custom' : draft.background} options={[{ value: '', label: '无背景' }, { value: 'blue', label: '晴空蓝' }, { value: 'violet', label: '浅紫' }, { value: 'mint', label: '薄荷' }, ...(isImage ? [{ value: 'custom', label: '自定义图片' }] : [])]} onChange={value => setDraft({ ...draft, background: value })} /><label className="flex cursor-pointer items-center rounded-md border border-[var(--color-border)] px-3 text-sm focus-within:ring-2 focus-within:ring-blue-300">上传图片<input aria-label="上传背景图" type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={event => { upload(event.target.files?.[0]); event.target.value = ''; }} /></label></div><span className="mt-1 block text-xs text-[var(--color-text-3)]">PNG / JPEG / WebP，最大 1 MB</span></div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">{(Object.keys(widgetNames) as WidgetType[]).filter(type => !draft.widgets.some(item => item.type === type)).map(type => <Button key={type} size="small" icon={<PlusOutlined />} onClick={() => setDraft({ ...draft, widgets: [...draft.widgets, { type, width: 6 }] })}>{widgetNames[type]}</Button>)}</div>
    </section>}
    <div className="grid grid-cols-12 gap-5">
      {visibleWidgets.map((item, index) => <section key={item.type} draggable={Boolean(draft) && !search.trim()} onDragStart={event => { if ((event.target as HTMLElement).closest('button,input,a')) { event.preventDefault(); return; } setDragged(index); }} onDragOver={event => { if (draft && dragged !== undefined) event.preventDefault(); }} onDrop={event => { event.preventDefault(); if (dragged !== undefined) move(dragged, index); setDragged(undefined); }} onDragEnd={() => setDragged(undefined)} className={`col-span-12 min-w-0 rounded-xl border bg-[var(--color-bg)] p-5 ${item.width === 6 ? 'lg:col-span-6' : ''} ${draft ? 'border-dashed border-blue-300' : 'border-[var(--color-border)]'}`}>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
          <h2 className="m-0 flex items-center gap-2 text-sm font-semibold"><span className="text-blue-500">{icons[item.type]}</span>{widgetNames[item.type]}</h2>
          {draft && !search.trim() ? <div className="flex items-center gap-1"><HolderOutlined className="cursor-grab text-[var(--color-text-3)]" /><Select aria-label={`${widgetNames[item.type]}宽度`} size="small" value={item.width} options={[{ value: 6, label: '半宽' }, { value: 12, label: '整行' }]} onChange={width => setDraft({ ...draft, widgets: draft.widgets.map((w, i) => i === index ? { ...w, width } : w) })} /><Button size="small" aria-label={`上移${widgetNames[item.type]}`} disabled={index === 0} icon={<ArrowUpOutlined />} onClick={() => move(index, index - 1)} /><Button size="small" aria-label={`下移${widgetNames[item.type]}`} disabled={index === draft.widgets.length - 1} icon={<ArrowDownOutlined />} onClick={() => move(index, index + 1)} /><Button size="small" aria-label={`移除${widgetNames[item.type]}`} icon={<DeleteOutlined />} onClick={() => setDraft({ ...draft, widgets: draft.widgets.filter((_, i) => i !== index) })} /></div> : (item.type === 'todo' || item.type === 'tickets') && dashboard.can_view_tickets ? <Link className="text-xs" href={item.type === 'todo' ? '/itsm/tickets?tab=mine' : '/itsm/tickets'}>查看全部</Link> : null}
        </div>
        {widget(item.type)}
      </section>)}
    </div>
    {!visibleWidgets.length && <Empty description="暂无工作台组件" />}
  </div>;
}
