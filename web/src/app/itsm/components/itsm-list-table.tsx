'use client';

import { useState, type ComponentProps } from 'react';
import CustomTable from '@/components/custom-table';

/** 已完整加载的管理列表共用 BK-Lite 表格分页；工单中心使用服务端分页。 */
export default function ItsmListTable<T extends object>({ dataSource = [], ...props }: Omit<ComponentProps<typeof CustomTable<T>>, 'pagination'>) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const current = Math.min(page, Math.max(1, Math.ceil(dataSource.length / pageSize)));
  return <CustomTable<T> scroll={{ y: 'calc(100vh - 320px)' }} {...props} dataSource={dataSource.slice((current - 1) * pageSize, current * pageSize)}
    pagination={{ current, pageSize, total: dataSource.length, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], onChange: (next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size); } }} />;
}
