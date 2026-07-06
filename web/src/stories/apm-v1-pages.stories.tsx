import type { Meta, StoryObj } from '@storybook/nextjs';
import React from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Flex,
  Input,
  Layout,
  List,
  Progress,
  Row,
  Segmented,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import {
  ApartmentOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  ClusterOutlined,
  ExclamationCircleOutlined,
  RadarChartOutlined,
  SearchOutlined,
  WarningOutlined,
} from '@ant-design/icons';

const { Header, Sider, Content } = Layout;
const { Title, Paragraph, Text } = Typography;

const shellStyles = {
  minHeight: '100vh',
  background: '#f3f7fb',
};

const contentShellStyle = {
  padding: 24,
};

const pageSectionStyle: React.CSSProperties = {
  marginBottom: 20,
};

function ModuleSider({ current }: { current: string }) {
  const items = [
    { key: 'home', label: '首页', icon: <RadarChartOutlined /> },
    { key: 'services', label: '服务目录', icon: <ApartmentOutlined /> },
    { key: 'traces', label: 'Trace 查询', icon: <SearchOutlined /> },
    { key: 'integrations', label: '接入中心', icon: <ApiOutlined /> },
  ];

  return (
    <Sider width={232} style={{ background: '#ffffff', borderRight: '1px solid #e7edf4' }}>
      <div style={{ padding: '22px 18px 12px' }}>
        <Title level={4} style={{ margin: 0 }}>
          BK-Lite APM
        </Title>
        <Text type="secondary">v1 页面稿</Text>
      </div>
      <div style={{ padding: '8px 10px 18px' }}>
        {items.map((item) => {
          const active = item.key === current;
          return (
            <div
              key={item.key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                borderRadius: 12,
                padding: '11px 12px',
                marginBottom: 8,
                background: active ? '#eaf2ff' : 'transparent',
                color: active ? '#1f6fff' : '#31506e',
                fontWeight: active ? 600 : 500,
              }}
            >
              {item.icon}
              <span>{item.label}</span>
            </div>
          );
        })}
      </div>
    </Sider>
  );
}

function PageFrame({
  current,
  title,
  subtitle,
  right,
  children,
}: {
  current: string;
  title: string;
  subtitle: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Layout style={shellStyles}>
      <ModuleSider current={current} />
      <Layout>
        <Header
          style={{
            background: '#ffffff',
            borderBottom: '1px solid #e7edf4',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <Title level={3} style={{ margin: 0 }}>
              {title}
            </Title>
            <Text type="secondary">{subtitle}</Text>
          </div>
          <div>{right}</div>
        </Header>
        <Content style={contentShellStyle}>{children}</Content>
      </Layout>
    </Layout>
  );
}

function StatTrendCard({
  title,
  value,
  suffix,
  tone = 'default',
  note,
}: {
  title: string;
  value: string;
  suffix?: string;
  tone?: 'default' | 'danger' | 'warn' | 'ok';
  note: string;
}) {
  const toneMap = {
    default: '#1f6fff',
    danger: '#dc2626',
    warn: '#d97706',
    ok: '#16a34a',
  };

  return (
    <Card bordered={false} style={{ borderRadius: 20, boxShadow: '0 10px 26px rgba(29,49,76,0.06)' }}>
      <Statistic title={title} value={value} suffix={suffix} valueStyle={{ color: toneMap[tone], fontWeight: 700 }} />
      <Text type="secondary">{note}</Text>
    </Card>
  );
}

function HomePageMock() {
  const namespaceColumns = [
    { title: '业务系统', dataIndex: 'namespace', key: 'namespace' },
    { title: '异常服务', dataIndex: 'services', key: 'services' },
    { title: '疑似回归版本', dataIndex: 'versions', key: 'versions' },
    { title: '建议动作', dataIndex: 'action', key: 'action' },
  ];

  const namespaceData = [
    { key: '1', namespace: 'monitor', services: '3', versions: '2', action: '优先进入 monitor-api 服务详情' },
    { key: '2', namespace: 'billing', services: '1', versions: '1', action: '确认 payment-worker 下游延迟' },
    { key: '3', namespace: 'cmdb', services: '0', versions: '0', action: '当前正常' },
  ];

  return (
    <PageFrame
      current="home"
      title="首页"
      subtitle="值班调查台：先回答现在哪里最值得查"
      right={<Tag color="red">当前异常窗口：近 1 小时</Tag>}
    >
      <Row gutter={[16, 16]} style={pageSectionStyle}>
        <Col span={6}>
          <StatTrendCard title="异常业务系统" value="2" tone="danger" note="monitor、billing 正在影响排障视图" />
        </Col>
        <Col span={6}>
          <StatTrendCard title="最可疑服务" value="monitor-api" tone="warn" note="错误率与 P95 同时劣化" />
        </Col>
        <Col span={6}>
          <StatTrendCard title="疑似版本回归" value="3" tone="danger" note="存在 service.version 且出现明显变化" />
        </Col>
        <Col span={6}>
          <StatTrendCard title="高风险资源" value="8" tone="default" note="优先看支付、告警、采集入口资源" />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={pageSectionStyle}>
        <Col span={16}>
          <Card title="当前异常业务系统" bordered={false} style={{ borderRadius: 20 }}>
            <Table pagination={false} columns={namespaceColumns} dataSource={namespaceData} />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="下一步建议" bordered={false} style={{ borderRadius: 20 }}>
            <Timeline
              items={[
                { color: 'red', children: '进入 monitor / monitor-api 服务详情' },
                { color: 'orange', children: '优先查看局部拓扑，判断是否是下游拖慢' },
                { color: 'blue', children: '跳到高风险资源 /api/v1/alerts/dispatch' },
                { color: 'green', children: '用版本对比确认 2026.06.26-rc3 是否回归' },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col span={12}>
          <Card title="高风险资源榜" bordered={false} style={{ borderRadius: 20 }}>
            <List
              dataSource={[
                'monitor-api /api/v1/alerts/dispatch',
                'payment-worker charge.execute',
                'monitor-scheduler /api/v1/tasks/sync',
                'billing-api POST /payments/confirm',
              ]}
              renderItem={(item, index) => (
                <List.Item>
                  <Space>
                    <Badge count={index + 1} color={index === 0 ? '#dc2626' : '#1f6fff'} />
                    <span>{item}</span>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="接入质量提醒" bordered={false} style={{ borderRadius: 20 }}>
            <Alert
              type="warning"
              showIcon
              message="存在 4 个未归类服务"
              description="这些服务已经上报 trace，但缺少 service.namespace，当前无法进入业务系统分组，也会影响拓扑聚合。"
            />
            <Divider />
            <Paragraph style={{ marginBottom: 0 }}>
              建议直接去 <Text strong>接入中心 / 最近发现的服务映射结果</Text>，确认 namespace、service.name、service.version 是否正确。
            </Paragraph>
          </Card>
        </Col>
      </Row>
    </PageFrame>
  );
}

function ServiceDirectoryMock() {
  const namespaces = [
    { name: 'monitor', health: 72, services: 12, issues: 3, active: true },
    { name: 'billing', health: 88, services: 8, issues: 1 },
    { name: 'cmdb', health: 99, services: 5, issues: 0 },
    { name: '未归类', health: 40, services: 4, issues: 4 },
  ];

  const serviceRows = [
    {
      key: 'monitor-api',
      service: 'monitor-api',
      namespace: 'monitor',
      status: 'critical',
      errorRate: '7.8%',
      p95: '2.6s',
      throughput: '1.8k/min',
      version: '2026.06.26-rc3',
      owner: 'SRE / Monitor',
    },
    {
      key: 'alert-engine',
      service: 'alert-engine',
      namespace: 'monitor',
      status: 'critical',
      errorRate: '5.1%',
      p95: '1.9s',
      throughput: '930/min',
      version: '2026.06.26-rc3',
      owner: 'Alert Team',
    },
    {
      key: 'monitor-scheduler',
      service: 'monitor-scheduler',
      namespace: 'monitor',
      status: 'warning',
      errorRate: '3.2%',
      p95: '1.7s',
      throughput: '420/min',
      version: '2026.06.26-rc1',
      owner: 'SRE / Monitor',
    },
    {
      key: 'billing-api',
      service: 'billing-api',
      namespace: 'billing',
      status: 'normal',
      errorRate: '0.6%',
      p95: '460ms',
      throughput: '760/min',
      version: '2026.06.20',
      owner: 'Billing Team',
    },
    {
      key: 'otel-gateway',
      service: 'otel-gateway',
      namespace: '未归类',
      status: 'mapping',
      errorRate: '-',
      p95: '-',
      throughput: '2.4k/min',
      version: 'unknown',
      owner: 'Platform',
    },
  ];

  const serviceColumns = [
    {
      title: '服务',
      dataIndex: 'service',
      key: 'service',
      render: (_: unknown, record: (typeof serviceRows)[number]) => (
        <div>
          <Space size={8}>
            <span style={{ color: '#1f2937', fontWeight: 700 }}>{record.service}</span>
            <ApmStatusTag status={record.status} />
          </Space>
          <div style={{ color: '#64748b', fontSize: 12, marginTop: 4 }}>
            {record.namespace} · {record.owner}
          </div>
        </div>
      ),
    },
    { title: '错误率', dataIndex: 'errorRate', key: 'errorRate', width: 92 },
    { title: 'P95', dataIndex: 'p95', key: 'p95', width: 90 },
    { title: '吞吐', dataIndex: 'throughput', key: 'throughput', width: 108 },
    { title: '版本', dataIndex: 'version', key: 'version', width: 145 },
    {
      title: '操作',
      key: 'action',
      width: 126,
      render: () => <a style={{ color: '#155aef', fontWeight: 600 }}>进入详情</a>,
    },
  ];

  const primaryNav = [
    { label: '服务目录', active: true },
    { label: 'Trace 查询' },
    { label: '接入中心' },
  ];

  const filterNav = [
    { label: '全部服务', active: true },
    { label: '异常服务' },
    { label: '未归类' },
  ];

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(180deg, #eaf4ff 0, #f7fbff 120px, #f4f7fb 121px)' }}>
      <div style={{ height: 56, display: 'grid', gridTemplateColumns: '260px 1fr 260px', alignItems: 'center', padding: '0 18px' }}>
        <Space size={10}>
          <img src="/logo-site.png" alt="BlueKing Lite" style={{ width: 34, height: 34, objectFit: 'contain' }} />
          <span style={{ color: '#334155', fontSize: 16, fontWeight: 700 }}>BlueKing Lite</span>
          <Button size="small" icon={<ClusterOutlined />} />
        </Space>
        <Space size={24} style={{ justifyContent: 'center', color: '#334155', fontWeight: 600 }}>
          {primaryNav.map((item) => (
            <a
              key={item.label}
              style={{
                color: item.active ? '#155aef' : '#334155',
                background: item.active ? '#fff' : 'transparent',
                padding: item.active ? '8px 14px' : '8px 0',
                borderRadius: 10,
              }}
            >
              {item.label === '服务目录' && <ApartmentOutlined />} {item.label === 'Trace 查询' && <SearchOutlined />} {item.label === '接入中心' && <ApiOutlined />} {item.label}
            </a>
          ))}
        </Space>
        <Space size={12} style={{ justifyContent: 'flex-end' }}>
          <Text type="secondary">陈润巍</Text>
          <span style={{ width: 28, height: 28, borderRadius: 14, background: '#155aef', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>陈</span>
        </Space>
      </div>

      <div style={{ display: 'flex', gap: 18, padding: '10px 18px 14px' }}>
        {filterNav.map((item) => (
          <button
            key={item.label}
            style={{
              height: 34,
              padding: '0 16px',
              borderRadius: 8,
              border: item.active ? '1px solid #e6eef8' : '1px solid transparent',
              background: item.active ? '#fff' : 'transparent',
              color: item.active ? '#155aef' : '#334155',
              fontWeight: 700,
              boxShadow: item.active ? '0 2px 8px rgba(15,23,42,0.04)' : 'none',
            }}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '252px minmax(760px,1fr)', gap: 16, padding: '0 18px 18px' }}>
        <aside style={{ display: 'grid', gap: 12, alignContent: 'start' }}>
          <div style={apmPanelStyle}>
            <Input placeholder="搜索业务系统 / 服务" suffix={<SearchOutlined style={{ color: '#155aef' }} />} />
            <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
              {namespaces.map((item) => (
                <button
                  key={item.name}
                  style={{
                    border: item.active ? '1px solid #155aef' : '1px solid #e6eef8',
                    background: item.active ? '#eef5ff' : '#fff',
                    borderRadius: 8,
                    padding: 10,
                    textAlign: 'left',
                  }}
                >
                  <Flex justify="space-between" align="center">
                    <span style={{ color: '#1f2937', fontWeight: 700 }}>{item.name}</span>
                    <span style={{ color: item.issues ? '#ef4444' : '#22c55e', fontWeight: 700 }}>{item.issues}</span>
                  </Flex>
                  <div style={{ color: '#64748b', fontSize: 12, marginTop: 4 }}>{item.services} 服务 · 健康度 {item.health}%</div>
                  <Progress percent={item.health} size="small" showInfo={false} strokeColor={item.health < 60 ? '#ef4444' : '#22c55e'} />
                </button>
              ))}
            </div>
          </div>

          <div style={apmPanelStyle}>
            <div style={sectionTitleStyle}>接入可信度</div>
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <TrustRow label="service.namespace" value="86%" status="warn" />
              <TrustRow label="trace/span" value="99%" status="ok" />
            </Space>
          </div>
        </aside>

        <main style={{ display: 'grid', gap: 12, alignContent: 'start' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 12 }}>
            <ApmMetric title="异常服务" value="3" note="monitor 优先" tone="danger" />
            <ApmMetric title="P95 最差" value="2.6s" note="monitor-api" tone="warn" />
            <ApmMetric title="未归类" value="4" note="影响服务分组" tone="warn" />
          </div>

          <div style={apmPanelStyle}>
            <Flex justify="space-between" align="center" style={{ marginBottom: 12 }}>
              <div>
                <div style={sectionTitleStyle}>服务清单</div>
                <div style={{ color: '#64748b', fontSize: 12 }}>按异常优先级排序，默认展示近 15 分钟活跃服务</div>
              </div>
              <Space>
                <Button type="primary">前往接入中心</Button>
              </Space>
            </Flex>
            <Table size="middle" pagination={false} columns={serviceColumns} dataSource={serviceRows} />
          </div>

          <div style={apmPanelStyle}>
            <div style={sectionTitleStyle}>接入问题</div>
            <Alert
              type="warning"
              showIcon
              message="4 个服务未归类"
              description="MVP 阶段只提示关键接入质量问题。优先修正 service.namespace，否则服务目录的业务分组会失真。"
            />
          </div>
        </main>
      </div>
    </div>
  );
}

const apmPanelStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #e6eef8',
  borderRadius: 8,
  padding: 14,
  boxShadow: '0 2px 8px rgba(15,23,42,0.04)',
};

const sectionTitleStyle: React.CSSProperties = {
  color: '#1f2937',
  fontSize: 16,
  fontWeight: 700,
  lineHeight: '24px',
};

function ApmStatusTag({ status }: { status: string }) {
  const map: Record<string, { color: string; label: string }> = {
    critical: { color: 'red', label: '异常' },
    warning: { color: 'orange', label: '关注' },
    mapping: { color: 'blue', label: '待归类' },
    normal: { color: 'green', label: '正常' },
  };
  const item = map[status] || map.normal;
  return <Tag color={item.color}>{item.label}</Tag>;
}

function ApmMetric({
  title,
  value,
  note,
  tone,
}: {
  title: string;
  value: string;
  note: string;
  tone: 'danger' | 'warn' | 'ok';
}) {
  const color = tone === 'danger' ? '#ef4444' : tone === 'warn' ? '#f59e0b' : '#22c55e';
  return (
    <div style={apmPanelStyle}>
      <div style={{ color: '#64748b', fontWeight: 600, marginBottom: 8 }}>{title}</div>
      <div style={{ color: '#1f2937', fontSize: 28, fontWeight: 800, lineHeight: '32px' }}>{value}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
        <span style={{ width: 8, height: 8, borderRadius: 4, background: color }} />
        <span style={{ color: '#64748b' }}>{note}</span>
      </div>
    </div>
  );
}

function TrustRow({
  label,
  value,
  status,
}: {
  label: string;
  value: string;
  status: 'ok' | 'warn';
}) {
  const percent = Number(value.replace('%', ''));
  return (
    <div>
      <Flex justify="space-between" align="center" style={{ marginBottom: 4 }}>
        <span style={{ color: '#334155' }}>{label}</span>
        <span style={{ color: status === 'ok' ? '#16a34a' : '#d97706', fontWeight: 700 }}>{value}</span>
      </Flex>
      <Progress percent={percent} size="small" showInfo={false} strokeColor={status === 'ok' ? '#22c55e' : '#f59e0b'} />
    </div>
  );
}

function MiniTopologyMap({ variant }: { variant: 'global' | 'local' }) {
  const global = variant === 'global';
  return (
    <div
      style={{
        position: 'relative',
        height: global ? 340 : 290,
        borderRadius: 18,
        border: '1px solid #dbe6f4',
        background: 'linear-gradient(180deg, #fbfdff 0%, #f4f8fe 100%)',
        overflow: 'hidden',
      }}
    >
      <NodeBox label="monitor-api" note="异常" top={global ? 120 : 110} left={global ? 230 : 240} tone="danger" center />
      <NodeBox label="auth-service" note="关注" top={global ? 36 : 30} left={global ? 82 : 90} tone="warn" />
      <NodeBox label="alert-engine" note="异常边" top={global ? 36 : 32} left={global ? 380 : 390} tone="danger" />
      <NodeBox label="billing-api" note="跨域依赖" top={global ? 208 : 195} left={global ? 80 : 100} tone="default" />
      <NodeBox label="redis-cache" note="下游" top={global ? 215 : 190} left={global ? 410 : 420} tone="warn" />
      {global && <NodeBox label="cmdb-sync" note="正常" top={250} left={600} tone="default" />}

      <EdgeLine top={112} left={150} width={126} rotate={35} tone="warn" label="上游流量增高" />
      <EdgeLine top={112} left={360} width={110} rotate={144} tone="danger" label="错误率高" />
      <EdgeLine top={198} left={160} width={118} rotate={-27} tone="default" label="跨域调用" />
      <EdgeLine top={202} left={352} width={126} rotate={23} tone="warn" label="P95 退化" />
      {global && <EdgeLine top={230} left={520} width={120} rotate={12} tone="default" label="正常邻接" />}
    </div>
  );
}

function NodeBox({
  label,
  note,
  top,
  left,
  tone,
  center,
}: {
  label: string;
  note: string;
  top: number;
  left: number;
  tone: 'default' | 'warn' | 'danger';
  center?: boolean;
}) {
  const colorMap = {
    default: '#8fb7ff',
    warn: '#f2c56a',
    danger: '#f0a8a8',
  };

  return (
    <div
      style={{
        position: 'absolute',
        top,
        left,
        minWidth: 122,
        padding: '10px 12px',
        borderRadius: 16,
        background: center ? '#f7fbff' : '#ffffff',
        border: `1px solid ${center ? '#1f6fff' : colorMap[tone]}`,
        boxShadow: '0 10px 20px rgba(35,52,74,0.06)',
        textAlign: 'center',
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{label}</div>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {note}
      </Text>
    </div>
  );
}

function EdgeLine({
  top,
  left,
  width,
  rotate,
  tone,
  label,
}: {
  top: number;
  left: number;
  width: number;
  rotate: number;
  tone: 'default' | 'warn' | 'danger';
  label: string;
}) {
  const colorMap = {
    default: '#a8b8cd',
    warn: '#e7ad33',
    danger: '#d95353',
  };
  return (
    <>
      <div
        style={{
          position: 'absolute',
          top,
          left,
          width,
          height: tone === 'default' ? 2 : 3,
          background: colorMap[tone],
          transform: `rotate(${rotate}deg)`,
          transformOrigin: 'left center',
        }}
      />
      <div
        style={{
          position: 'absolute',
          top: top + 8,
          left: left + width / 2 - 28,
          padding: '2px 8px',
          background: 'rgba(255,255,255,0.92)',
          borderRadius: 999,
          border: '1px solid #dbe6f4',
          color: '#5f7489',
          fontSize: 12,
        }}
      >
        {label}
      </div>
    </>
  );
}

function ServiceDetailMock() {
  return (
    <PageFrame
      current="services"
      title="monitor-api"
      subtitle="service.namespace = monitor · 从服务目录下钻进入的调查页"
      right={
        <Space>
          <Tag color="red">异常</Tag>
          <Tag color="orange">疑似版本回归</Tag>
          <Button type="primary">查看 Trace</Button>
        </Space>
      }
    >
      <Alert
        showIcon
        type="error"
        style={{ marginBottom: 16 }}
        message="当前服务在近 1 小时出现明显劣化"
        description="错误率从 0.9% 升至 7.8%，P95 从 420ms 升至 2.6s。建议优先查看局部拓扑中的 alert-engine 和 redis-cache 下游边。"
      />

      <Row gutter={[16, 16]} style={pageSectionStyle}>
        <Col span={6}>
          <StatTrendCard title="当前版本" value="2026.06.26-rc3" tone="warn" note="上一活跃版本为 2026.06.20" />
        </Col>
        <Col span={6}>
          <StatTrendCard title="错误率" value="7.8" suffix="%" tone="danger" note="最近 1 小时显著高于基线" />
        </Col>
        <Col span={6}>
          <StatTrendCard title="P95" value="2.6" suffix="s" tone="danger" note="慢请求主要集中于告警分发资源" />
        </Col>
        <Col span={6}>
          <StatTrendCard title="可疑边" value="2" tone="warn" note="alert-engine、redis-cache 均有退化" />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={pageSectionStyle}>
        <Col span={15}>
          <Card title="局部拓扑（默认一跳上下游）" bordered={false} style={{ borderRadius: 20 }}>
            <Paragraph type="secondary">
              这是拓扑调查模式，不是静态架构图。默认围绕当前异常服务、当前时间窗加载，并突出异常边。
            </Paragraph>
            <MiniTopologyMap variant="local" />
          </Card>
        </Col>
        <Col span={9}>
          <Card title="版本对比摘要" bordered={false} style={{ borderRadius: 20 }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="当前版本">2026.06.26-rc3</Descriptions.Item>
              <Descriptions.Item label="对比版本">2026.06.20</Descriptions.Item>
              <Descriptions.Item label="错误率变化">
                <Text type="danger">+6.9%</Text>
              </Descriptions.Item>
              <Descriptions.Item label="P95 变化">
                <Text type="danger">+2.18s</Text>
              </Descriptions.Item>
              <Descriptions.Item label="主要异常资源">/api/v1/alerts/dispatch</Descriptions.Item>
            </Descriptions>
          </Card>
          <Card title="轻量错误聚合" bordered={false} style={{ borderRadius: 20, marginTop: 16 }}>
            <List
              dataSource={[
                'TimeoutException · 主要影响 dispatch 资源 · 最近 5 分钟新增',
                'RedisWriteError · 当前版本更明显',
                'ValidationError · 数量稳定，优先级较低',
              ]}
              renderItem={(item, index) => (
                <List.Item>
                  <Space align="start">
                    {index === 0 ? <ExclamationCircleOutlined style={{ color: '#dc2626', marginTop: 3 }} /> : <WarningOutlined style={{ color: '#d97706', marginTop: 3 }} />}
                    <span>{item}</span>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      <Card title="高风险资源" bordered={false} style={{ borderRadius: 20 }}>
        <Table
          pagination={false}
          columns={[
            { title: '资源', dataIndex: 'resource', key: 'resource' },
            { title: '错误率', dataIndex: 'errorRate', key: 'errorRate' },
            { title: 'P95', dataIndex: 'p95', key: 'p95' },
            { title: '版本差异', dataIndex: 'delta', key: 'delta' },
            { title: '下一步', dataIndex: 'next', key: 'next' },
          ]}
          dataSource={[
            { key: '1', resource: '/api/v1/alerts/dispatch', errorRate: '12.1%', p95: '3.8s', delta: '明显升高', next: '进入资源详情' },
            { key: '2', resource: 'task.dispatch', errorRate: '6.4%', p95: '1.9s', delta: '中度升高', next: '看异常 Trace' },
          ]}
        />
      </Card>
    </PageFrame>
  );
}

function TraceQueryMock() {
  return (
    <PageFrame
      current="traces"
      title="Trace 查询"
      subtitle="证据层工作台：从服务、资源、拓扑异常边带上下文进入"
      right={<Tag color="blue">context: monitor-api / alert-engine 边</Tag>}
    >
      <Card bordered={false} style={{ borderRadius: 20, marginBottom: 16 }}>
        <Flex gap={12} wrap>
          <Input prefix={<SearchOutlined />} placeholder="服务 / Trace ID / 资源关键字" style={{ width: 280 }} />
          <Tag color="blue">namespace: monitor</Tag>
          <Tag color="red">service: monitor-api</Tag>
          <Tag color="orange">version: 2026.06.26-rc3</Tag>
          <Tag color="magenta">error = true</Tag>
          <Tag color="purple">latency &gt; 2s</Tag>
        </Flex>
      </Card>

      <Row gutter={[16, 16]}>
        <Col span={14}>
          <Card title="Trace 列表" bordered={false} style={{ borderRadius: 20 }}>
            <Table
              pagination={false}
              columns={[
                { title: '开始时间', dataIndex: 'time', key: 'time' },
                { title: '资源', dataIndex: 'resource', key: 'resource' },
                { title: '版本', dataIndex: 'version', key: 'version' },
                { title: '持续时长', dataIndex: 'duration', key: 'duration' },
                { title: '错误', dataIndex: 'error', key: 'error' },
              ]}
              dataSource={[
                { key: '1', time: '10:42:11', resource: '/api/v1/alerts/dispatch', version: '2026.06.26-rc3', duration: '4.8s', error: 'TimeoutException' },
                { key: '2', time: '10:41:56', resource: '/api/v1/alerts/dispatch', version: '2026.06.26-rc3', duration: '3.7s', error: 'RedisWriteError' },
                { key: '3', time: '10:41:12', resource: 'task.dispatch', version: '2026.06.26-rc3', duration: '2.4s', error: 'TimeoutException' },
              ]}
            />
          </Card>
        </Col>
        <Col span={10}>
          <Card title="单条 Trace 详情（证据层）" bordered={false} style={{ borderRadius: 20 }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Trace ID">9a52f85e4c3f</Descriptions.Item>
              <Descriptions.Item label="service.namespace">monitor</Descriptions.Item>
              <Descriptions.Item label="service.name">monitor-api</Descriptions.Item>
              <Descriptions.Item label="service.version">2026.06.26-rc3</Descriptions.Item>
              <Descriptions.Item label="错误类型">TimeoutException</Descriptions.Item>
            </Descriptions>
            <Divider />
            <Timeline
              items={[
                { color: 'blue', children: 'monitor-api /api/v1/alerts/dispatch · 420ms' },
                { color: 'red', children: 'alert-engine notify.send · 2.1s · error spike' },
                { color: 'orange', children: 'redis-cache redis.command · 1.6s · latency high' },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </PageFrame>
  );
}

function IntegrationCatalogMock() {
  const cards = [
    { title: 'Java', note: '传统 JVM 服务优先推荐', type: '主流语言', status: '已接入 12 个服务' },
    { title: 'Python', note: '适合 API 与任务服务', type: '主流语言', status: '已接入 7 个服务' },
    { title: 'Node.js', note: '适合网关与前后端中台', type: '主流语言', status: '接入中' },
    { title: 'Go', note: '适合高并发微服务', type: '主流语言', status: '未接入' },
    { title: 'OTel Collector', note: '适合已有采集网关', type: 'Collector', status: '建议迁移入口' },
    { title: 'Kubernetes 注解注入', note: '适合集群内批量接入', type: 'K8s', status: '试点推荐' },
    { title: 'eBPF 自动注入', note: '适合低侵入试点', type: '自动注入', status: '仅作快速观测入口' },
  ];

  return (
    <PageFrame
      current="integrations"
      title="接入中心"
      subtitle="标准化 OTLP 接入入口：不是纯文档页，而是接入路径选择器"
      right={<Segmented options={['全部', '主流语言', 'Collector', 'K8s', '自动注入']} defaultValue="全部" />}
    >
      <Card bordered={false} style={{ borderRadius: 20, marginBottom: 16 }}>
        <Input prefix={<SearchOutlined />} placeholder="搜索语言、Collector、接入方式" />
      </Card>
      <Row gutter={[16, 16]}>
        {cards.map((card) => (
          <Col span={8} key={card.title}>
            <Card bordered={false} style={{ borderRadius: 20, minHeight: 200 }}>
              <Flex justify="space-between" align="center">
                <Space>
                  <ClusterOutlined style={{ color: '#1f6fff' }} />
                  <Title level={4} style={{ margin: 0 }}>
                    {card.title}
                  </Title>
                </Space>
                <Tag>{card.type}</Tag>
              </Flex>
              <Paragraph type="secondary" style={{ minHeight: 46 }}>
                {card.note}
              </Paragraph>
              <Divider />
              <Text strong>{card.status}</Text>
              <Paragraph type="secondary" style={{ marginTop: 10, marginBottom: 0 }}>
                进入详情后可拿到 OTLP 端点、接入凭证、配置模板和最近发现的服务映射结果。
              </Paragraph>
            </Card>
          </Col>
        ))}
      </Row>
    </PageFrame>
  );
}

function IntegrationDetailMock() {
  return (
    <PageFrame
      current="integrations"
      title="Java 接入详情"
      subtitle="不是只教你怎么接，还要告诉你为什么还没接好"
      right={
        <Space>
          <Tag color="red">接入异常</Tag>
          <Button>重新自检</Button>
        </Space>
      }
    >
      <Row gutter={[16, 16]} style={pageSectionStyle}>
        <Col span={12}>
          <Card title="接入自检" bordered={false} style={{ borderRadius: 20 }}>
            <List
              dataSource={[
                { title: '接入凭证', desc: '已生成有效 token', status: 'ok' },
                { title: '传输与准入', desc: '认证通过，但上报链路存在波动', status: 'warn' },
                { title: '数据接收', desc: '最近 30 分钟仅收到少量 trace', status: 'warn' },
                { title: '字段规范', desc: '发现 2 个服务缺少 service.namespace', status: 'danger' },
                { title: '分析可用性', desc: '服务已出现，但版本对比与拓扑部分降级', status: 'danger' },
              ]}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    avatar={
                      item.status === 'ok' ? (
                        <CheckCircleOutlined style={{ color: '#16a34a' }} />
                      ) : item.status === 'warn' ? (
                        <WarningOutlined style={{ color: '#d97706' }} />
                      ) : (
                        <ExclamationCircleOutlined style={{ color: '#dc2626' }} />
                      )
                    }
                    title={item.title}
                    description={item.desc}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="最近发现的服务映射结果" bordered={false} style={{ borderRadius: 20 }}>
            <List
              dataSource={[
                'monitor / monitor-api / 2026.06.26-rc3',
                'monitor / monitor-scheduler / 2026.06.26-rc1',
                '未归类 / alert-adapter / 2026.06.25',
                '未归类 / otel-gateway / version 缺失',
              ]}
              renderItem={(item, index) => (
                <List.Item>
                  <Space>
                    {index < 2 ? <Tag color="green">已归类</Tag> : <Tag color="red">未归类</Tag>}
                    <Text>{item}</Text>
                  </Space>
                </List.Item>
              )}
            />
            <Alert
              style={{ marginTop: 12 }}
              type="info"
              showIcon
              message="这块是 v1 的关键补充"
              description="它直接回答“平台最近认出了什么”，避免用户明明上报了 trace，却不知道为什么服务没出现在预期业务系统里。"
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col span={10}>
          <Card title="接入凭证与 OTLP 端点" bordered={false} style={{ borderRadius: 20 }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="token">obk_••••••••••</Descriptions.Item>
              <Descriptions.Item label="OTLP endpoint">https://otlp.bklite.cloud/v1/traces</Descriptions.Item>
              <Descriptions.Item label="认证头">Authorization: Bearer obk_••••••</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col span={14}>
          <Card title="接入配置" bordered={false} style={{ borderRadius: 20 }}>
            <Tabs
              items={[
                {
                  key: 'agent',
                  label: 'Java Agent',
                  children: (
                    <pre style={codeBlockStyle}>
{`export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.bklite.cloud
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <token>"
export OTEL_RESOURCE_ATTRIBUTES="service.namespace=monitor,service.name=monitor-api,service.version=2026.06.26-rc3"
java -javaagent:./opentelemetry-javaagent.jar -jar app.jar`}
                    </pre>
                  ),
                },
                {
                  key: 'docker',
                  label: 'Docker',
                  children: (
                    <pre style={codeBlockStyle}>
{`docker run -e OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.bklite.cloud \\
  -e OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <token>" \\
  -e OTEL_RESOURCE_ATTRIBUTES="service.namespace=monitor,service.name=monitor-api,service.version=2026.06.26-rc3" app:latest`}
                    </pre>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </PageFrame>
  );
}

const codeBlockStyle: React.CSSProperties = {
  margin: 0,
  padding: 16,
  borderRadius: 16,
  background: '#0f172a',
  color: '#dbeafe',
  fontSize: 13,
  lineHeight: 1.7,
  overflowX: 'auto',
};

const meta = {
  title: 'APM/V1 Pages',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const HomeDutyConsole: Story = {
  render: () => <HomePageMock />,
};

export const ServiceDirectory: Story = {
  render: () => <ServiceDirectoryMock />,
};

export const ServiceDetail: Story = {
  render: () => <ServiceDetailMock />,
};

export const TraceWorkbench: Story = {
  render: () => <TraceQueryMock />,
};

export const IntegrationCatalog: Story = {
  render: () => <IntegrationCatalogMock />,
};

export const IntegrationDetail: Story = {
  render: () => <IntegrationDetailMock />,
};
