'use client';

import { useState, type ComponentProps } from 'react';
import CustomTable from '@/components/custom-table';

type ListTableProps<T extends object> = Omit<ComponentProps<typeof CustomTable<T>>, 'pagination'> & {
  /** 搜索或分组切换时回首页，保留每页条数。 */
  queryKey?: string;
};

/** 已完整加载的管理列表共用 BK-Lite 表格分页；工单中心使用服务端分页。 */
export default function ItsmListTable<T extends object>({ dataSource = [], queryKey = '', ...props }: ListTableProps<T>) {
  const [position, setPosition] = useState({ page: 1, queryKey });
  const [pageSize, setPageSize] = useState(20);
  if (position.queryKey !== queryKey) setPosition({ page: 1, queryKey });
  const page = position.queryKey === queryKey ? position.page : 1;
  const current = Math.min(page, Math.max(1, Math.ceil(dataSource.length / pageSize)));
  return <CustomTable<T> scroll={{ y: 'calc(100vh - 320px)' }} {...props} dataSource={dataSource.slice((current - 1) * pageSize, current * pageSize)}
    pagination={{ current, pageSize, total: dataSource.length, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], onChange: (next, size) => { setPosition({ page: size === pageSize ? next : 1, queryKey }); setPageSize(size); } }} />;
}
