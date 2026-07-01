import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button, Form, Input, InputNumber, Select, Switch, Table, Tabs } from 'antd';
import { DownloadOutlined, PlusOutlined } from '@ant-design/icons';

const tableShellStyle = {
  border: '1px solid #e5e7eb',
  borderRadius: 6,
  overflow: 'hidden',
  background: '#fff',
};

const columnsBase = [
  {
    title: '节点',
    dataIndex: 'node',
    width: 220,
    render: () => <Select style={{ width: '100%' }} placeholder="请选择节点" />,
  },
  {
    title: '实例名称',
    dataIndex: 'instance',
    width: 220,
    render: () => <Input placeholder="实例名称" />,
  },
  {
    title: '组',
    dataIndex: 'group',
    width: 220,
    render: () => <Select style={{ width: '100%' }} placeholder="请选择组" />,
  },
  {
    title: '操作',
    dataIndex: 'action',
    width: 120,
    fixed: 'right' as const,
    render: () => (
      <Button type="link" size="small" icon={<PlusOutlined />}>
        添加
      </Button>
    ),
  },
];

const pingColumns = [
  columnsBase[0],
  {
    title: '目标地址',
    dataIndex: 'target',
    width: 340,
    render: () => <Input placeholder="example.com / 192.168.1.1 / 2001:db8::1" />,
  },
  ...columnsBase.slice(1),
];

const websiteColumns = [
  columnsBase[0],
  {
    title: 'URL（IPv4/IPv6）',
    dataIndex: 'url',
    width: 420,
    render: () => <Input placeholder="https://example.com 或 https://[2001:db8::1]/" />,
  },
  ...columnsBase.slice(1),
];

const rows = [{ key: 'draft' }];

const ProbePanel = ({
  title,
  description,
  columns,
  showTlsSkip,
  objectHint,
}: {
  title: string;
  description: string;
  columns: any[];
  showTlsSkip?: boolean;
  objectHint: string;
}) => (
  <div style={{ padding: 24, background: '#f8fafc', minHeight: 620 }}>
    <section
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        background: '#fff',
        padding: '20px 24px',
        marginBottom: 16,
      }}
    >
      <div style={{ fontSize: 20, fontWeight: 700, color: '#1f2937' }}>{title}</div>
      <div style={{ marginTop: 8, color: '#64748b', fontSize: 14 }}>{description}</div>
    </section>

    <section
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        background: '#fff',
        padding: 24,
      }}
    >
      <div style={{ marginBottom: 18, fontSize: 16, fontWeight: 700, color: '#111827' }}>采集配置</div>
      <Form layout="vertical">
        <div style={{ display: 'flex', gap: 32, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <Form.Item
            required
            label="间隔"
            extra={<span style={{ color: '#64748b' }}>监控数据的采集时间间隔，单位：秒</span>}
          >
            <InputNumber min={1} precision={0} defaultValue={10} addonAfter="s" style={{ width: 300 }} />
          </Form.Item>
          {showTlsSkip && (
            <Form.Item
              label="跳过证书校验"
              extra={<span style={{ color: '#64748b' }}>HTTPS 场景下是否跳过服务端证书校验</span>}
            >
              <Switch />
            </Form.Item>
          )}
        </div>
      </Form>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          margin: '24px 0 10px',
        }}
      >
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#111827' }}>监控对象</div>
          <div style={{ marginTop: 4, color: '#64748b', fontSize: 13 }}>
            {objectHint}
          </div>
        </div>
        <Button type="primary" icon={<DownloadOutlined />}>
          导入
        </Button>
      </div>

      <div style={tableShellStyle}>
        <Table
          size="middle"
          pagination={false}
          columns={columns}
          dataSource={rows}
          scroll={{ x: columns.reduce((total, column) => total + Number(column.width || 150), 0) }}
        />
      </div>
    </section>
  </div>
);

export const PingProbe = () => (
  <ProbePanel
    title="Ping（Telegraf）"
    description="通过 ICMP 回显请求检查目标主机或网络设备连通性；自动识别 IPv6 字面量。"
    columns={pingColumns}
    objectHint="每行对应一个拨测实例；Ping 会自动识别 IPv6 字面量。"
  />
);

export const WebsiteProbe = () => (
  <ProbePanel
    title="网站拨测（Telegraf）"
    description="通过 HTTP/HTTPS 连接检查可用性和性能；IPv6 URL 使用方括号格式。"
    columns={websiteColumns}
    showTlsSkip
    objectHint="每行对应一个拨测实例；IPv6 URL 需使用方括号格式。"
  />
);

export const ProbeAccessFrame = () => (
  <Tabs
    defaultActiveKey="ping"
    items={[
      { key: 'ping', label: 'Ping 拨测', children: <PingProbe /> },
      { key: 'website', label: '网站拨测', children: <WebsiteProbe /> },
    ]}
  />
);

const meta: Meta<typeof ProbeAccessFrame> = {
  title: 'Monitor/ProbeAccess',
  component: ProbeAccessFrame,
  parameters: {
    layout: 'fullscreen',
  },
};

export default meta;

type Story = StoryObj<typeof ProbeAccessFrame>;

export const Default: Story = {};
