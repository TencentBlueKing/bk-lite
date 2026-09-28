import type { Meta, StoryObj } from '@storybook/nextjs';
import { Tag } from 'antd';
import { useState } from 'react';
import type { Key } from 'react';

import DualSelector from '@/components/dual-selector';

interface ResourceRow {
  id: string;
  name: string;
  address: string;
  source: string;
}

const records: ResourceRow[] = [
  { id: 'node:1', name: 'inspection-linux-01', address: '172.18.0.20', source: '节点管理' },
  { id: 'node:2', name: 'inspection-linux-02', address: '172.18.0.21', source: '节点管理' },
  { id: 'manual:11', name: 'job-linux-01', address: '10.10.41.101', source: '作业平台' },
];

function DualSelectorContract({ initiallyEmpty = false }: { initiallyEmpty?: boolean }) {
  const [selectedKeys, setSelectedKeys] = useState<Key[]>(initiallyEmpty ? [] : ['node:1', 'manual:11']);
  const selectedRecords = records.filter((record) => selectedKeys.includes(record.id));

  return (
    <div className="h-[520px] p-6">
      <DualSelector<ResourceRow>
        rowKey="id"
        dataSource={records}
        columns={[
          { title: '资源名称', dataIndex: 'name' },
          { title: '地址', dataIndex: 'address' },
        ]}
        selectedKeys={selectedKeys}
        onChange={setSelectedKeys}
        selectedRecordsData={selectedRecords}
        pagination={false}
        rightTitle={`已选 ${selectedKeys.length} 项`}
        clearAllText="全部清除"
        emptySelectionText="暂未选择"
        selectedPreviewLabel="已选项预览"
        renderSelectedItem={(record) => <div><div className="truncate font-medium text-[var(--color-text-1)]">{record.name}</div><div className="mt-1 flex items-center gap-1.5 text-xs text-[var(--color-text-3)]"><span className="font-mono">{record.address}</span><Tag className="!m-0">{record.source}</Tag></div></div>}
        getRemoveLabel={(record) => `移除 ${record.name}`}
        height="100%"
      />
    </div>
  );
}

const meta = {
  title: 'Components/Data Display/DualSelector',
  component: DualSelectorContract,
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof DualSelectorContract>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { args: {} };

export const EmptySelection: Story = { args: { initiallyEmpty: true } };
