'use client';

import CustomTable from '@/components/custom-table';

const rows = [{ id: 1, title: '示例工单', status: '新' }];

export default function TicketsPage() {
  return (
    <CustomTable
      rowKey="id"
      dataSource={rows}
      columns={[
        { title: '标题', dataIndex: 'title', key: 'title' },
        { title: '状态', dataIndex: 'status', key: 'status' },
      ]}
    />
  );
}
