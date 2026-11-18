'use client';

import { useEffect, useRef, useState, type ComponentProps } from 'react';
import CustomTable from '@/components/custom-table';

type ListTableProps<T extends object> = Omit<ComponentProps<typeof CustomTable<T>>, 'pagination'> & {
  /** 搜索或分组切换时回首页，保留每页条数。 */
  queryKey?: string;
  storageKey?: string;
};

/** 已完整加载的管理列表共用 BK-Lite 表格分页；工单中心使用服务端分页。 */
export default function ItsmListTable<T extends object>({ dataSource = [], queryKey = '', storageKey, ...props }: ListTableProps<T>) {
  const container=useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ page: 1, queryKey });
  const [pageSize, setPageSize] = useState(20);
  useEffect(()=>{
    if (!storageKey) return;
    try {const saved=JSON.parse(sessionStorage.getItem(storageKey)||'null');if(saved?.queryKey===queryKey){setPosition({page:saved.page,queryKey});setPageSize(saved.pageSize);}} catch { /* 无缓存时使用默认分页。 */ }
  },[storageKey,queryKey]);
  useEffect(()=>{
    if (!storageKey || !dataSource.length) return;
    try {const saved=JSON.parse(sessionStorage.getItem(storageKey+':scroll')||'null');const body=container.current?.querySelector('.ant-table-body');if(body && saved?.queryKey===queryKey)body.scrollTop=saved.top;} catch { /* 缓存无效时从顶部开始。 */ }
  },[storageKey,queryKey,dataSource.length]);
  if (position.queryKey !== queryKey) setPosition({ page: 1, queryKey });
  const page = position.queryKey === queryKey ? position.page : 1;
  const current = Math.min(page, Math.max(1, Math.ceil(dataSource.length / pageSize)));
  return <div ref={container} onScrollCapture={event=>{if(storageKey && (event.target as HTMLElement).classList.contains('ant-table-body'))sessionStorage.setItem(storageKey+':scroll',JSON.stringify({queryKey,top:(event.target as HTMLElement).scrollTop}));}}><CustomTable<T> scroll={{ y: 'calc(100vh - 320px)' }} {...props} dataSource={dataSource.slice((current - 1) * pageSize, current * pageSize)}
    pagination={{ current, pageSize, total: dataSource.length, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], onChange: (next, size) => { setPosition({ page: size === pageSize ? next : 1, queryKey }); setPageSize(size); if(storageKey)sessionStorage.setItem(storageKey,JSON.stringify({page:size===pageSize?next:1,pageSize:size,queryKey})); } }} /></div>;
}
