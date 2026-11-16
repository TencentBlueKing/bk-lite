'use client';

import { AppstoreOutlined, ArrowRightOutlined, StarFilled, StarOutlined } from '@ant-design/icons';
import { Button, Empty, Pagination, Tag, TreeSelect } from 'antd';
import Link from 'next/link';
import { useState } from 'react';
import type { PortalData, PortalService } from '../types';
import type { PortalDashboard, PortalTicket } from './workbench-types';

export function ServiceCards({ items, portal, onFavorite, pending, paginate = false }: { paginate?: boolean; items: PortalService[]; portal: PortalData; onFavorite: (id: number) => void; pending?: number }) {
  const favorites = new Set(portal.favorites.map(item => item.id));
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const current = Math.min(page, Math.max(1, Math.ceil(items.length / pageSize)));
  if (!items.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无服务" />;
  return <><div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 240px), 1fr))" }}>
    {(paginate ? items.slice((current - 1) * pageSize, current * pageSize) : items).map((item, index) => <div key={item.id} className="group flex gap-3 rounded-xl border border-[var(--color-border)] p-4 transition-shadow hover:shadow-md">
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg ${['bg-blue-50 text-blue-600', 'bg-indigo-50 text-indigo-600', 'bg-cyan-50 text-cyan-600'][index % 3]}`}><AppstoreOutlined /></span>
      <div className="min-w-0 flex-1">
        {portal.can_apply ? <Link href={`/itsm/tickets/new?service_id=${item.id}`} className="font-medium text-[var(--color-text-1)] hover:text-[var(--color-primary)]">{item.name}<ArrowRightOutlined className="ml-2 text-xs opacity-0 group-hover:opacity-100" /></Link> : <span className="font-medium">{item.name}</span>}
        <p className="mb-0 mt-2 line-clamp-2 text-xs leading-5 text-[var(--color-text-3)]">{item.description || item.workflow_name || '按需申请，在线跟进处理进度'}</p>
      </div>
      <Button type="text" size="small" aria-label={`${favorites.has(item.id) ? '取消收藏' : '收藏'}${item.name}`} title={favorites.has(item.id) ? '取消收藏' : '收藏'} loading={pending === item.id} disabled={pending !== undefined} icon={favorites.has(item.id) ? <StarFilled className="text-amber-400" /> : <StarOutlined className="text-[var(--color-text-3)]" />} onClick={() => onFavorite(item.id)} />
    </div>)}
  </div>{paginate && items.length > 10 && <Pagination className="mt-4 flex justify-end" current={current} pageSize={pageSize} total={items.length} showSizeChanger pageSizeOptions={[10, 20, 50, 100]} onChange={(next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size); }} />}</>;
}

export function ServiceBrowser({ portal, search, onFavorite, pending }: { portal: PortalData; search: string; onFavorite: (id: number) => void; pending?: number }) {
  const [catalog, setCatalog] = useState<number | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const selected = new Set<number>(catalog === undefined ? [] : [catalog]);
  // 包含子目录；循环目录数据也不会使页面卡死。
  for (let i = 0; i < portal.catalogs.length; i++) {
    let added = false;
    portal.catalogs.forEach(item => { if (item.parent_id !== null && selected.has(item.parent_id) && !selected.has(item.id)) { selected.add(item.id); added = true; } });
    if (!added) break;
  }
  const filtered = portal.services.filter(item => (catalog === undefined || (catalog === 0 ? !item.catalog_id : selected.has(item.catalog_id || 0))) && `${item.name} ${item.description || ''} ${item.workflow_name || ''}`.toLowerCase().includes(search.trim().toLowerCase()));
  const current = Math.min(page, Math.max(1, Math.ceil(filtered.length / pageSize)));
  const shown = filtered.slice((current - 1) * pageSize, current * pageSize);
  const groups = [...new Set(shown.map(item => item.catalog_id))];
  return <div>
    <div className="mb-4 flex items-center justify-between gap-3">
      <span className="text-xs text-[var(--color-text-3)]">选择服务，开始你的申请</span>
      <TreeSelect aria-label="服务目录筛选" className="w-48" allowClear showSearch treeNodeFilterProp="title" treeDataSimpleMode placeholder="全部目录" value={catalog} onChange={value => { setCatalog(value); setPage(1); }} treeData={[{ id: 0, pId: null, value: 0, title: '未分类' }, ...portal.catalogs.map(item => ({ id: item.id, pId: item.parent_id, value: item.id, title: item.name }))]} />
    </div>
    {!shown.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={search ? '未找到匹配的服务，试试其他关键词' : '暂无可申请的服务'} /> : groups.map(id => <section key={id || 0} className="mb-4 last:mb-0">
      <h3 className="mb-3 text-xs font-medium text-[var(--color-text-3)]">{portal.catalogs.find(item => item.id === id)?.name || '其他服务'}</h3>
      <ServiceCards items={shown.filter(item => item.catalog_id === id)} portal={portal} onFavorite={onFavorite} pending={pending} />
    </section>)}
    {filtered.length > 10 && <Pagination className="mt-4 flex justify-end" current={current} pageSize={pageSize} total={filtered.length} showSizeChanger pageSizeOptions={[10, 20, 50, 100]} onChange={(next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size); }} />}
  </div>;
}

export function TicketRows({ items, allowed }: { items: PortalTicket[]; allowed?: boolean }) {
  if (!items.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={allowed === false ? '暂无工单查看权限' : '暂无工单'} />;
  return <div className="divide-y divide-[var(--color-border)]">{items.map(item => <Link key={item.id} href={`/itsm/tickets/${item.id}`} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
    <div className="min-w-0 flex-1"><div className="truncate text-sm text-[var(--color-text-1)]">{item.title}</div><div className="mt-1 text-xs text-[var(--color-text-3)]">{item.sn}</div></div><Tag className="m-0 shrink-0" color="blue">{item.status}</Tag>
  </Link>)}</div>;
}

export function TrendChart({ data }: { data: PortalDashboard['trend'] }) {
  const max = Math.max(1, ...data.flatMap(item => [item.created, item.finished]));
  const point = (value: number, index: number) => `${36 + index * 424 / Math.max(data.length - 1, 1)},${150 - value / max * 120}`;
  return <div>
    <div className="mb-2 flex gap-4 text-xs text-[var(--color-text-3)]"><span className="text-blue-500">● 新建</span><span className="text-emerald-500">● 完成</span><span className="ml-auto">近 14 天</span></div>
    <svg viewBox="0 0 480 184" className="w-full" role="img" aria-label="近十四天新建与完成工单趋势">
      {[0, 0.5, 1].map(ratio => <g key={ratio}><line x1="36" y1={150 - ratio * 120} x2="460" y2={150 - ratio * 120} stroke="var(--color-border)" strokeDasharray="4 4" /><text x="24" y={154 - ratio * 120} textAnchor="end" fontSize="10" fill="var(--color-text-3)">{Math.round(max * ratio)}</text></g>)}
      {(['created', 'finished'] as const).map((key, i) => <g key={key}><polyline fill="none" stroke={i ? '#10b981' : '#3b82f6'} strokeWidth="2.5" strokeLinejoin="round" points={data.map((item, index) => point(item[key], index)).join(' ')} />{data.map((item, index) => { const [cx, cy] = point(item[key], index).split(','); return <circle key={item.date} cx={cx} cy={cy} r="4" fill={i ? '#10b981' : '#3b82f6'} tabIndex={0}><title>{item.date}：新建 {item.created}，完成 {item.finished}</title></circle>; })}</g>)}
      {data.filter((_, i) => i % 3 === 0 || i === data.length - 1).map(item => <text key={item.date} x={point(0, data.indexOf(item)).split(',')[0]} y="176" textAnchor="middle" fontSize="10" fill="var(--color-text-3)">{item.date.slice(5)}</text>)}
    </svg>
    <p className="mb-0 text-xs text-[var(--color-text-3)]">完成量按记录的完成时间统计；历史工单未记录完成时间的不计入趋势。</p>
  </div>;
}
