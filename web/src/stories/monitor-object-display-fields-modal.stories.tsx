import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button, Input, Modal, Radio, Select, Space, Tag } from 'antd';
import {
  CloseOutlined,
  HolderOutlined,
  PlusOutlined,
} from '@ant-design/icons';

const pluginOptions = [
  { label: '主机（Telegraf）', value: 'telegraf' },
  { label: 'Windows WMI', value: 'wmi' },
  { label: '主机远程采集（Telegraf）', value: 'remote' },
];

const metricOptions = [
  { label: 'CPU使用率', value: 'cpu_usage' },
  { label: '节点信息', value: 'node_info' },
];

const fieldOptions = ['collector_ip', 'model', 'os_name', 'agent_id'];

function BindingRow({ field }: { field?: string }) {
  return (
    <div className="flex items-center gap-2 pl-6">
      <Select className="flex-1" value="telegraf" options={pluginOptions} />
      <Select
        className="flex-1"
        value={field ? 'node_info' : 'cpu_usage'}
        options={metricOptions}
      />
      {field && (
        <Input
          className="flex-1"
          value={field}
          addonAfter={
            <Button type="link" size="small" className="px-0">
              选择字段
            </Button>
          }
        />
      )}
      <Button type="text" danger icon={<CloseOutlined />} />
    </div>
  );
}

function ColumnBlock({
  title,
  tag,
  field,
}: {
  title: string;
  tag: string;
  field?: string;
}) {
  return (
    <div className="rounded border border-[#d9d9d9] bg-[#f5f7fa] p-3">
      <div className="mb-2 flex items-center gap-2">
        <HolderOutlined className="cursor-move text-[#8c8c8c]" />
        <Input className="flex-1" value={title} />
        <Tag color={field ? 'geekblue' : 'blue'}>{tag}</Tag>
        <Button type="text" danger icon={<CloseOutlined />} />
      </div>
      <div className="space-y-2">
        <BindingRow field={field} />
        <BindingRow field={field} />
      </div>
      <Button
        type="dashed"
        size="small"
        icon={<PlusOutlined />}
        className="ml-6 mt-2"
      >
        添加指标
      </Button>
    </div>
  );
}

function DisplayFieldsModalPreview() {
  return (
    <div className="min-h-[760px] bg-[#eef2f6] p-8">
      <div className="mx-auto w-[900px] rounded bg-white shadow-[0_12px_32px_rgba(0,0,0,0.18)]">
        <div className="flex h-14 items-center justify-between border-b border-[#edf0f5] px-5">
          <strong>展示指标配置 - 主机</strong>
          <CloseOutlined className="text-[#8c8c8c]" />
        </div>
        <div className="p-5">
          <div className="mb-3 flex justify-end gap-2">
            <Button icon={<PlusOutlined />}>添加指标列</Button>
            <Button icon={<PlusOutlined />}>添加展示列</Button>
          </div>
          <div className="space-y-3">
            <ColumnBlock title="CPU使用率" tag="指标列" />
            <ColumnBlock title="采集节点IP" tag="展示列" field="collector_ip" />
            <ColumnBlock title="设备型号" tag="展示列" field="model" />
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-[#edf0f5] px-5 py-4">
          <Button>取消</Button>
          <Button type="primary">确认</Button>
        </div>
      </div>
      <Modal title="选择字段" open footer={null} width={420}>
        <Radio.Group value="collector_ip">
          <Space direction="vertical">
            {fieldOptions.map((field) => (
              <Radio key={field} value={field}>
                {field}
              </Radio>
            ))}
          </Space>
        </Radio.Group>
      </Modal>
    </div>
  );
}

const meta: Meta<typeof DisplayFieldsModalPreview> = {
  title: 'Monitor/Object/Display Fields Modal',
  component: DisplayFieldsModalPreview,
  parameters: {
    layout: 'fullscreen',
  },
};

export default meta;

type Story = StoryObj<typeof DisplayFieldsModalPreview>;

export const Default: Story = {};
