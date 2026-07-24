import type { Meta, StoryObj } from '@storybook/nextjs';

import { Button, message } from 'antd';

import CustomTable from '@/components/custom-table';

const meta: Meta<typeof CustomTable> = {
  component: CustomTable,
};

export default meta;

type Story = StoryObj<typeof CustomTable>;

export const Default: Story = {
  args: {
    dataSource: [
      {
        key: '1',
        name: 'John Brown',
        age: 32,
        address: 'New York No. 1 Lake Park',
      },
      {
        key: '2',
        name: 'Jim Green',
        age: 42,
        address: 'London No. 1 Lake Park',
      },
    ],
    columns: [
      {
        title: 'Name',
        dataIndex: 'name',
        key: 'name',
      },
      {
        title: 'Age',
        dataIndex: 'age',
        key: 'age',
      },
      {
        title: 'Address',
        dataIndex: 'address',
        key: 'address',
      },
    ],
  },
};


export const TableWithButton: Story = {
  args: {
    bordered: true,
    dataSource: [
      {
        key: '1',
        name: 'John Brown',
        age: 32,
        address: 'New York No. 1 Lake Park',
      },
      {
        key: '2',
        name: 'Jim Green',
        age: 42,
        address: 'London No. 1 Lake Park',
      },
    ],
    columns: [
      {
        title: 'Name',
        dataIndex: 'name',
        key: 'name',
      },
      {
        title: 'Age',
        dataIndex: 'age',
        key: 'age',
      },
      {
        title: 'Address',
        dataIndex: 'address',
        key: 'address',
      },
      {
        title: 'Action',
        key: 'action',
        render: () => (
          <Button onClick={() => message.info('Button clicked!')}>Click Me</Button>
        ),
      },
    ],
  },
};

const preferenceColumns = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '上报时间', dataIndex: 'time', key: 'time' },
  { title: 'CPU 使用率', dataIndex: 'cpu', key: 'metric:cpu' },
  { title: '内存使用率', dataIndex: 'memory', key: 'metric:memory' },
];

export const SearchableFieldSettings: Story = {
  args: {
    pagination: false,
    dataSource: [
      {
        key: '1',
        name: 'fusion-collector',
        time: '2026-07-24 10:00:00',
        cpu: '31.70%',
        memory: '59.38%',
      },
    ],
    columns: preferenceColumns,
    fieldSetting: {
      showSetting: true,
      displayFieldKeys: ['name', 'time', 'metric:cpu'],
      choosableFields: preferenceColumns,
      searchable: true,
      modalWidth: 900,
      groupFields: [
        {
          title: '基础信息',
          key: 'basic',
          child: preferenceColumns.slice(0, 2),
        },
        {
          title: '指标信息',
          key: 'metric',
          child: preferenceColumns.slice(2),
        },
      ],
    },
    onSelectFields: async () => undefined,
  },
};
