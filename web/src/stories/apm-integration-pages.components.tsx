import React, { useState } from 'react';
import {
  Alert,
  Button,
  Col,
  Form,
  Input,
  Layout,
  Radio,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ApiOutlined,
  ArrowLeftOutlined,
  CodeOutlined,
  CopyOutlined,
  ExperimentOutlined,
  EyeOutlined,
  GlobalOutlined,
  PlusOutlined,
  RocketOutlined,
  SearchOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';

const { Content } = Layout;
const { Title, Text } = Typography;

/* ============================================================
 * bklite APM · 集成 · 交互式故事书
 *
 * 关键架构(已对齐规格书《集成.md》):
 *  1) 接入方式总览:SDK / OTC / eBPF / K8s 四组;SDK 下分 Node/Java/Python/.NET/Go 五种
 *  2) 接入详情页:顶部接入自检 4 项 + 中部 5 步任务路径 + 底部"上报端点 / 接入配置"双 tab
 *  3) 不带同比 delta;5 步完成状态由后端"近窗判定"实时计算,不依赖用户手动勾选
 *  4) 上报端点 OTLP/HTTP + OTLP/gRPC,平台统一分配,不允许自定义
 *  5) 资源属性 service.name + service.namespace 联合唯一,缺一不计入服务目录
 * ============================================================ */

const TOKENS = {
  bg: '#f5f7fa',
  surface: '#ffffff',
  border: '#e6ebf2',
  borderStrong: '#dbe2ec',
  text: '#1f2937',
  textSecondary: '#64748b',
  textTertiary: '#94a3b8',
  primary: '#155aef',
  primarySoft: '#eaf2ff',
  success: '#27c274',
  danger: '#f43b2c',
  warning: '#f59e0b',
  neutral: '#94a3b8',
};

const shellStyle: React.CSSProperties = {
  minHeight: '100vh',
  background: TOKENS.bg,
  fontFamily:
    'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
};

const surfaceCardStyle: React.CSSProperties = {
  background: TOKENS.surface,
  border: `1px solid ${TOKENS.border}`,
  borderRadius: 12,
};

const codeBlockStyle: React.CSSProperties = {
  background: '#0f172a',
  color: '#e2e8f0',
  padding: '14px 16px',
  borderRadius: 8,
  fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
  fontSize: 12,
  lineHeight: 1.7,
  whiteSpace: 'pre',
  overflowX: 'auto',
  position: 'relative',
};

/* ---------- 跨 Story URL ----------
 * 集成页拆为两个子目录后,story id 路径里带中文
 * (apm-integration-pages-添加接入 / apm-integration-pages-接入列表),
 * 这里集中维护跳转地址,不要在页面里散写。
 */
const STORY_URLS = {
  home: '?path=/story/apm-home-pages--home-dashboard-story',
  service: '?path=/story/apm-service-pages--service-directory-app-view',
  topology: '?path=/story/apm-service-pages--service-topology',
  explore: '?path=/story/apm-explore-pages--traces-search',
  events: '?path=/story/apm-events-pages--alerts-list',
  integration: '?path=/story/apm-integration-pages-添加接入--integration-catalog-story',
  integrationList: '?path=/story/apm-integration-pages-接入列表--integration-instance-list-story',
  integrationJava: '?path=/story/apm-integration-pages-添加接入--integration-detail-java',
  integrationNode: '?path=/story/apm-integration-pages-添加接入--integration-detail-node',
  integrationOtc: '?path=/story/apm-integration-pages-添加接入--integration-detail-otc',
};

/* ============================================================
 * 集成菜单 · 二级导航(添加接入 / 接入列表)
 * ============================================================ */
function IntegrationSubNav({ active }: { active: 'add' | 'list' }) {
  const items = [
    { key: 'add', label: '添加接入', href: STORY_URLS.integration },
    { key: 'list', label: '接入列表', href: STORY_URLS.integrationList },
  ];
  return (
    <div
      style={{
        background: TOKENS.surface,
        borderBottom: `1px solid ${TOKENS.border}`,
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        height: 44,
      }}
    >
      {items.map((it) => {
        const isActive = it.key === active;
        return (
          <a
            key={it.key}
            href={it.href}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '0 12px',
              height: 44,
              color: isActive ? TOKENS.primary : TOKENS.text,
              borderBottom: isActive ? `2px solid ${TOKENS.primary}` : '2px solid transparent',
              fontSize: 14,
              fontWeight: isActive ? 600 : 500,
              textDecoration: 'none',
            }}
          >
            {it.key === 'add' && <PlusOutlined />}
            {it.key === 'list' && <UnorderedListOutlined />}
            <span>{it.label}</span>
          </a>
        );
      })}
    </div>
  );
}

/* ============================================================
 * 顶导(全局)
 * ============================================================ */
function TopMenuBar({ active = 'integration' }: { active?: string }) {
  const items = [
    { key: 'home', label: '首页', icon: <RocketOutlined />, href: STORY_URLS.home },
    { key: 'service', label: '服务', icon: <ApiOutlined />, href: STORY_URLS.service },
    { key: 'explore', label: '探索', icon: <ExperimentOutlined />, href: STORY_URLS.explore },
    { key: 'events', label: '事件', icon: <SettingOutlined />, href: STORY_URLS.events },
    { key: 'integration', label: '集成', icon: <RocketOutlined />, href: STORY_URLS.integration },
  ];
  return (
    <div
      style={{
        background: TOKENS.surface,
        borderBottom: `1px solid ${TOKENS.border}`,
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        height: 52,
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      <div
        style={{
          fontSize: 15,
          fontWeight: 600,
          color: TOKENS.primary,
          marginRight: 24,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <RocketOutlined style={{ fontSize: 18 }} />
        <span>BK-Lite APM</span>
      </div>
      {items.map((it) => {
        const isActive = it.key === active;
        return (
          <a
            key={it.key}
            href={it.href}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '0 12px',
              height: 52,
              color: isActive ? TOKENS.primary : TOKENS.text,
              background: isActive ? TOKENS.primarySoft : 'transparent',
              borderBottom: isActive ? `2px solid ${TOKENS.primary}` : '2px solid transparent',
              fontSize: 14,
              fontWeight: isActive ? 600 : 500,
              textDecoration: 'none',
            }}
          >
            {it.icon}
            <span>{it.label}</span>
          </a>
        );
      })}
    </div>
  );
}

/* ============================================================
 * 接入方式总览(SDK / OTC / eBPF / K8s 四组)
 * ============================================================ */
type IntegrationKind =
  | 'node'
  | 'java'
  | 'python'
  | 'dotnet'
  | 'go'
  | 'otc'
  | 'ebpf'
  | 'k8s';

const INTEGRATION_GROUPS: Array<{
  group: string;
  icon: React.ReactNode;
  items: Array<{ kind: IntegrationKind; title: string; desc: string; tag?: string }>;
}> = [
  {
    group: 'SDK',
    icon: <CodeOutlined />,
    items: [
      { kind: 'node', title: 'Node.js', desc: '零代码自动探针接入,支持 Express / Nest / Koa / Fastify', tag: '推荐' },
      { kind: 'java', title: 'Java', desc: '字节码注入零代码接入,支持 Spring / Dubbo / gRPC', tag: '推荐' },
      { kind: 'python', title: 'Python', desc: '运行时 SDK 接入,支持 Django / Flask / FastAPI' },
      { kind: 'dotnet', title: '.NET', desc: '基于 OpenTelemetry .NET 自动探针' },
      { kind: 'go', title: 'Go', desc: '编译期引入 SDK 接入,需在代码中埋点' },
    ],
  },
  {
    group: 'OTC',
    icon: <ApiOutlined />,
    items: [
      { kind: 'otc', title: 'OTel Collector(链路)', desc: '已有自建 Collector?改它的 exporter 把链路推到本平台' },
    ],
  },
  {
    group: 'eBPF',
    icon: <ExperimentOutlined />,
    items: [
      { kind: 'ebpf', title: 'eBPF 自动注入(OBI)', desc: '无需改代码,内核态 eBPF 自动捕获服务链路', tag: '低侵入' },
    ],
  },
  {
    group: 'K8s',
    icon: <GlobalOutlined />,
    items: [
      { kind: 'k8s', title: 'Kubernetes 注册注入(OTel Operator)', desc: '装一次 Operator,给 Pod 打一行注解即零代码注入探针' },
    ],
  },
];

function IntegrationCard({
  kind,
  title,
  desc,
  tag,
}: {
  kind: IntegrationKind;
  title: string;
  desc: string;
  tag?: string;
}) {
  const href =
    kind === 'java' ? STORY_URLS.integrationJava : kind === 'node' ? STORY_URLS.integrationNode : kind === 'otc' ? STORY_URLS.integrationOtc : '#';
  return (
    <a
      href={href}
      style={{
        ...surfaceCardStyle,
        padding: '16px 18px',
        display: 'block',
        textDecoration: 'none',
        height: '100%',
        transition: 'border-color 120ms, box-shadow 120ms',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}
      >
        <Title level={5} style={{ margin: 0, color: TOKENS.text }}>
          {title}
        </Title>
        {tag && (
          <Tag color="blue" style={{ margin: 0 }}>
            {tag}
          </Tag>
        )}
      </div>
      <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.6 }}>
        {desc}
      </Text>
      <div style={{ marginTop: 12, color: TOKENS.primary, fontSize: 12 }}>查看接入详情 →</div>
    </a>
  );
}

function IntegrationCatalog() {
  return (
    <div style={shellStyle}>
      <TopMenuBar active="integration" />
      <IntegrationSubNav active="add" />
      <Content style={{ padding: 24 }}>
        <div style={{ ...surfaceCardStyle, padding: '14px 16px', marginBottom: 16 }}>
          <Space size={8} align="center">
            <RocketOutlined style={{ color: TOKENS.primary }} />
            <Title level={4} style={{ margin: 0 }}>
              接入方式总览
            </Title>
            <Text type="secondary" style={{ fontSize: 12 }}>
              按环境选择最合适的接入方式 · 点击进入对应详情
            </Text>
          </Space>
        </div>
        <Space direction="vertical" size={20} style={{ width: '100%' }}>
          {INTEGRATION_GROUPS.map((g) => (
            <div key={g.group}>
              <Space size={8} align="center" style={{ marginBottom: 10 }}>
                {g.icon}
                <Title level={5} style={{ margin: 0 }}>
                  {g.group}
                </Title>
                <Tag style={{ margin: 0 }}>{g.items.length} 种</Tag>
              </Space>
              <Row gutter={[12, 12]}>
                {g.items.map((it) => (
                  <Col xs={24} sm={12} lg={8} xl={6} key={it.kind}>
                    <IntegrationCard {...it} />
                  </Col>
                ))}
              </Row>
            </div>
          ))}
        </Space>
        <Alert
          showIcon
          type="info"
          style={{ marginTop: 20, borderRadius: 8 }}
          message="APM 不向业务侧签发任何凭证或鉴权 token；区域 Collector 的 OTLP 入口鉴权由部署环境的 mTLS / Header 配置治理，APM 业务层不参与鉴权决策。"
        />
      </Content>
    </div>
  );
}

/* ============================================================
 * 接入详情页 · 通用 5 个功能区
 *  1) 顶部接入自检 4 项
 *  2) 中部 5 步任务路径
 *  3) "接通后先核对" + "跨服务不断链" 双栏
 *  4) 底部"上报端点 / 接入配置" 双 tab

/* ============================================================
 * 上报端点 / 接入配置 双 tab
 * ============================================================ */

/** 模拟服务端按云区域解析出的区域 Collector 端点。 */
const REGION_ENDPOINTS: Record<string, string> = {
  default: 'https://apm.bklite.cloud:4318',
  cn_north: 'https://apm.cn-north.bklite.cloud:4318',
  cn_east: 'https://apm.cn-east.bklite.cloud:4318',
  hk: 'https://apm.hk.bklite.cloud:4318',
  global: 'https://apm.global.bklite.cloud:4318',
};

const OTC_TRACES_ENDPOINTS: Record<string, string> = {
  default: 'https://apm.bklite.cloud:4318/v1/traces',
  cn_north: 'https://apm.cn-north.bklite.cloud:4318/v1/traces',
  cn_east: 'https://apm.cn-east.bklite.cloud:4318/v1/traces',
  hk: 'https://apm.hk.bklite.cloud:4318/v1/traces',
  global: 'https://apm.global.bklite.cloud:4318/v1/traces',
};

function EndpointPanel({
  region,
  setRegion,
  orgs,
  setOrgs,
  endpointMap = REGION_ENDPOINTS,
}: {
  region: string;
  setRegion: (v: string) => void;
  orgs: string[];
  setOrgs: (v: string[]) => void;
  endpointMap?: Record<string, string>;
}) {
  const endpoint = endpointMap[region] ?? endpointMap.default ?? Object.values(endpointMap)[0];
  return (
    <div>
      <Form layout="vertical" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item
              label={
                <span>
                  云区域 <span style={{ color: TOKENS.danger }}>*</span>
                </span>
              }
              style={{ marginBottom: 0 }}
            >
              <Select
                value={region}
                onChange={setRegion}
                style={{ width: '100%' }}
                options={[
                  { value: 'default', label: 'default' },
                  { value: 'cn_north', label: 'cn-north(华北)' },
                  { value: 'cn_east', label: 'cn-east(华东)' },
                  { value: 'hk', label: 'hk(香港)' },
                  { value: 'global', label: 'global(海外)' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item
              label={
                <span>
                  组织 <span style={{ color: TOKENS.danger }}>*</span>
                </span>
              }
              style={{ marginBottom: 0 }}
            >
              <Select
                mode="multiple"
                value={orgs}
                onChange={setOrgs}
                style={{ width: '100%' }}
                placeholder="选择组织(可多选)"
                options={[
                  { value: 'Default', label: 'Default' },
                  { value: 'finance', label: 'finance' },
                  { value: 'ops', label: 'ops' },
                  { value: 'platform', label: 'platform' },
                ]}
              />
            </Form.Item>
          </Col>
        </Row>
      </Form>
      <Title level={5} style={{ margin: 0, marginBottom: 8 }}>
        API 端点
      </Title>
      <div style={codeBlockStyle}>
        <span
          style={{
            background: TOKENS.success,
            color: '#fff',
            padding: '2px 8px',
            borderRadius: 3,
            fontSize: 11,
            fontWeight: 600,
            position: 'absolute',
            top: 12,
            left: 12,
            fontFamily: 'ui-monospace, monospace',
          }}
        >
          POST
        </span>
        <span
          style={{
            marginLeft: 64,
            display: 'inline-block',
            lineHeight: '36px',
            color: '#e2e8f0',
            fontFamily: 'ui-monospace, monospace',
            fontSize: 13,
          }}
        >
          {endpoint}
        </span>
        <Button
          size="small"
          type="text"
          icon={<CopyOutlined />}
          style={{ position: 'absolute', top: 8, right: 8, color: '#94a3b8' }}
        />
      </div>
    </div>
  );
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  return (
    <div style={codeBlockStyle}>
      <Tag
        style={{
          position: 'absolute',
          top: 8,
          left: 8,
          background: 'rgba(255,255,255,0.1)',
          color: '#cbd5e1',
          border: 'none',
          fontSize: 10,
        }}
      >
        {language}
      </Tag>
      <Button
        size="small"
        type="text"
        icon={<CopyOutlined />}
        style={{ position: 'absolute', top: 8, right: 8, color: '#94a3b8' }}
      />
      <pre style={{ margin: 0, marginTop: 20 }}>{code}</pre>
    </div>
  );
}

/** Java 接入配置(Java Agent / Docker 运行,-e 注入) */
const JAVA_AGENT_CODE = (endpoint: string) => `# 1. 下载官方 Java agent(一次性)
curl -fsSLO https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar

# 2. 配置上报(端点/资源属性走标准 OTEL_* 环境变量)
export OTEL_EXPORTER_OTLP_ENDPOINT=${endpoint}
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_PROPAGATORS=tracecontext,baggage
export OTEL_RESOURCE_ATTRIBUTES=service.name=my-service,service.namespace=电商主站,deployment.environment=production,service.version=1.0.0

# 3. 挂 -javaagent 启动(字节码注入,不改业务代码)
java -javaagent:./opentelemetry-javaagent.jar -jar app.jar`;

const JAVA_DOCKER_CODE = (endpoint: string) => `# 1. 在镜像里加自动探针(java 段,写进你的 Dockerfile):
#    ADD https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar /otel.jar
#    ENV JAVA_TOOL_OPTIONS=-javaagent:/otel.jar

# 2. 运行容器:端点/资源属性经 -e 注入
docker run \\
  -e OTEL_EXPORTER_OTLP_ENDPOINT=${endpoint} \\
  -e OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \\
  -e OTEL_PROPAGATORS=tracecontext,baggage \\
  -e OTEL_RESOURCE_ATTRIBUTES=service.name=my-service,service.namespace=电商主站,deployment.environment=production,service.version=1.0.0 \\
  your-image:latest`;

function JavaConfigPanel({ endpoint }: { endpoint: string }) {
  return (
    <SdkConfigPanel
      agentLabel="Java Agent"
      endpoint={endpoint}
      agentContent={(ep) => <CodeBlock language="BASH" code={JAVA_AGENT_CODE(ep)} />}
      dockerContent={(ep) => <CodeBlock language="BASH" code={JAVA_DOCKER_CODE(ep)} />}
    />
  );
}

/** SDK 接入通用组件:自动探针 + Docker 运行(对齐 Java 形态)
 *  两种模式切换:① 自动探针(语言原生方式) ② Docker 运行(-e 注入)
 *  endpoint 由调用方(IntegrationDetail) 注入,所有 SDK 接入方式都共享同一份 region 联动
 */
function SdkConfigPanel({
  agentLabel,
  agentContent,
  dockerContent,
  endpoint,
  defaultMode = 'agent',
}: {
  agentLabel: string;
  agentContent: (endpoint: string) => React.ReactNode;
  dockerContent: (endpoint: string) => React.ReactNode;
  endpoint: string;
  defaultMode?: 'agent' | 'docker';
}) {
  const [mode, setMode] = useState<'agent' | 'docker'>(defaultMode);
  return (
    <div>
      <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 12 }}>
        按下方片段配置上报,几分钟即可看到数据进来
      </Text>
      <div
        style={{
          background: TOKENS.primarySoft,
          padding: 4,
          borderRadius: 6,
          marginBottom: 8,
          display: 'inline-flex',
        }}
      >
        <Segmented
          value={mode}
          onChange={(v) => setMode(v as 'agent' | 'docker')}
          options={[
            { value: 'agent', label: agentLabel },
            { value: 'docker', label: 'Docker 运行(-e 注入)' },
          ]}
        />
      </div>
      {mode === 'agent' && (
        <div>
          <div style={{ fontSize: 12, color: TOKENS.textSecondary, marginBottom: 6 }}>
            {agentLabel}
          </div>
          {agentContent(endpoint)}
        </div>
      )}
      {mode === 'docker' && (
        <div>
          <div style={{ fontSize: 12, color: TOKENS.textSecondary, marginBottom: 6 }}>
            Docker 运行(-e 注入)
          </div>
          {dockerContent(endpoint)}
        </div>
      )}
    </div>
  );
}

function NodeConfigPanel({ endpoint }: { endpoint: string }) {
  return (
    <SdkConfigPanel
      agentLabel="Node.js 自动探针"
      endpoint={endpoint}
      agentContent={(ep) => (
        <CodeBlock
          language="BASH"
          code={`# 1. 装零代码自动探针
npm install @opentelemetry/auto-instrumentations-node

# 2. 配置上报(端点/资源属性走标准 OTEL_* 环境变量)
export OTEL_EXPORTER_OTLP_ENDPOINT=${ep}
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_PROPAGATORS=tracecontext,baggage
export OTEL_RESOURCE_ATTRIBUTES=service.name=my-service,service.namespace=电商主站,deployment.environment=production,service.version=1.0.0

# 3. 用 --require 预加载探针后照常启动(不改业务代码)
node --require @opentelemetry/auto-instrumentations-node/register app.js`}
        />
      )}
      dockerContent={(ep) => (
        <CodeBlock
          language="BASH"
          code={`docker run \\
  --name my-service \\
  -p 3000:3000 \\
  -e OTEL_EXPORTER_OTLP_ENDPOINT=${ep} \\
  -e OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \\
  -e OTEL_PROPAGATORS=tracecontext,baggage \\
  -e OTEL_RESOURCE_ATTRIBUTES=service.name=my-service,service.namespace=电商主站,deployment.environment=production,service.version=1.0.0 \\
  -e NODE_OPTIONS="--require @opentelemetry/auto-instrumentations-node/register" \\
  your-image:latest`}
        />
      )}
    />
  );
}

function OtcConfigPanel({ endpoint }: { endpoint: string }) {
  return (
    <div>
      <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 12 }}>
        按下方片段配置上报,几分钟即可看到数据进来
      </Text>
      <div style={{ fontSize: 13, fontWeight: 600, color: TOKENS.text, marginBottom: 4 }}>
        Collector exporter 配置
      </div>
      <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 10 }}>
        在已有 Collector 的 exporters / service 段追加以下内容
      </Text>
      <CodeBlock
        language="YAML"
        code={`exporters:
  otlphttp/saas:
    traces_endpoint: ${endpoint}

service:
  pipelines:
    traces:
      exporters: [otlphttp/saas]`}
      />
    </div>
  );
}

function EbpfConfigPanel() {
  return (
    <div>
      <Alert
        showIcon
        type="warning"
        style={{ marginBottom: 12, borderRadius: 6 }}
        message="eBPF 模式无需改代码,内核态自动捕获;但需要特权 Pod 或节点级部署,适合低侵入试点。"
      />
      <CodeBlock
        code={`# 1. 部署 OBI(OpenTelemetry eBPF Instrumentation)
kubectl apply -f https://github.com/open-telemetry/opentelemetry-go-instrumentation/releases/latest/download/obc.yaml

# 2. 配置 OTLP exporter
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_SERVICE_NAME=auto-instrumented
export OTEL_SERVICE_NAMESPACE=default
export OTEL_SERVICE_VERSION=v1.0.0

# 3. 启动 OBI
obi --config ./obi-config.yaml`}
        language="shell"
      />
    </div>
  );
}

function K8sConfigPanel() {
  return (
    <div>
      <Alert
        showIcon
        type="info"
        style={{ marginBottom: 12, borderRadius: 6 }}
        message="K8s 模式下装一次 OTel Operator,给 Pod 打一行注解即零代码注入探针,适合集群内批量接入。"
      />
      <CodeBlock
        code={`# 1. 安装 OTel Operator
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm install opentelemetry-operator open-telemetry/opentelemetry-operator

# 2. 创建 Instrumentation CR
apiVersion: opentelemetry.io/v1alpha1
kind: Instrumentation
metadata:
  name: default-instrumentation
spec:
  exporter:
    otlp:
      endpoint: https://otlp.bklite.cloud
  resource:
    addResourceAttributes:
      - deployment.environment=prod
  propagators:
    - tracecontext
    - baggage

# 3. 在 Pod 上加注解启用注入
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-svc
  annotations:
    instrumentation.opentelemetry.io/inject-java: "true"
spec:
  ...
`}
        language="yaml"
      />
    </div>
  );
}

function PythonConfigPanel({ endpoint }: { endpoint: string }) {
  return (
    <SdkConfigPanel
      agentLabel="Python 自动探针"
      endpoint={endpoint}
      agentContent={(ep) => (
        <CodeBlock
          language="BASH"
          code={`# 1. 装零代码自动探针与 OTLP 导出器
pip install opentelemetry-distro[otlp]

# 2. 自动检测依赖,写回 requirements.txt
opentelemetry-bootstrap -a requirements.txt

# 3. 配置上报(端点/资源属性走标准 OTEL_* 环境变量)
export OTEL_EXPORTER_OTLP_ENDPOINT=${ep}
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_PROPAGATORS=tracecontext,baggage
export OTEL_RESOURCE_ATTRIBUTES=service.name=my-service,service.namespace=电商主站,deployment.environment=production,service.version=1.0.0

# 4. 用 opentelemetry-instrument 包装启动(零代码自动注入)
opentelemetry-instrument python app.py`}
        />
      )}
      dockerContent={(ep) => (
        <CodeBlock
          language="BASH"
          code={`# 镜像内需装好 opentelemetry-distro 与 opentelemetry-instrument
docker run \\
  --name my-service \\
  -p 8000:8000 \\
  -e OTEL_EXPORTER_OTLP_ENDPOINT=${ep} \\
  -e OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \\
  -e OTEL_PROPAGATORS=tracecontext,baggage \\
  -e OTEL_RESOURCE_ATTRIBUTES=service.name=my-service,service.namespace=电商主站,deployment.environment=production,service.version=1.0.0 \\
  -e ENTRYPOINT=opentelemetry-instrument \\
  your-image:latest \\
  python app.py`}
        />
      )}
    />
  );
}

function DotnetConfigPanel({ endpoint }: { endpoint: string }) {
  return (
    <SdkConfigPanel
      agentLabel=".NET 自动探针(含 Windows/IIS)"
      endpoint={endpoint}
      agentContent={(ep) => (
        <CodeBlock
          language="BASH"
          code={`# 1. 装零代码自动探针(opentelemetry-dotnet-instrumentation)
curl -fsSLO https://github.com/open-telemetry/opentelemetry-dotnet-instrumentation/releases/latest/download/otel-dotnet-auto-install.sh -O
sh ./otel-dotnet-auto-install.sh

# 2. 配置上报(端点/资源属性走标准 OTEL_* 环境变量)
export OTEL_EXPORTER_OTLP_ENDPOINT=${ep}
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_PROPAGATORS=tracecontext,baggage
export OTEL_RESOURCE_ATTRIBUTES=service.name=my-service,service.namespace=电商主站,deployment.environment=production,service.version=1.0.0

# 3. source instrument.sh 注入后照常启动(不改业务代码)
. $HOME/.otel-dotnet-auto/instrument.sh
dotnet run

# Windows / IIS:改用 PowerShell 模块注册(管理员),之后 iisreset 目标应用池:
#   Import-Module OpenTelemetry.DotNet.Auto.psm1
#   Register-OpenTelemetryForIIS`}
        />
      )}
      dockerContent={(ep) => (
        <CodeBlock
          language="BASH"
          code={`# 镜像需先执行一次 otel-dotnet-auto-install.sh 以安装 instrument.sh
docker run \\
  --name my-service \\
  -p 5000:5000 \\
  -e OTEL_EXPORTER_OTLP_ENDPOINT=${ep} \\
  -e OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \\
  -e OTEL_PROPAGATORS=tracecontext,baggage \\
  -e OTEL_RESOURCE_ATTRIBUTES=service.name=my-service,service.namespace=电商主站,deployment.environment=production,service.version=1.0.0 \\
  your-image:latest \\
  bash -c ". /root/.otel-dotnet-auto/instrument.sh && dotnet run"`}
        />
      )}
    />
  );
}

function GoConfigPanel({ endpoint }: { endpoint: string }) {
  return (
    <SdkConfigPanel
      agentLabel="Go SDK(编译期引入)"
      endpoint={endpoint}
      agentContent={(ep) => (
        <CodeBlock
          language="BASH"
          code={`# 1. 装 OpenTelemetry SDK 与 OTLP 导出器
go get \\
  go.opentelemetry.io/otel \\
  go.opentelemetry.io/otel/sdk \\
  go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp \\
  go.opentelemetry.io/otel/semconv/v1.26.0

# 2. main.go 启动期初始化 tracer provider
#    资源属性 = service.name + service.namespace + deployment.environment + service.version
cat <<'EOF' > tracing.go
package main

import (
  "context"
  "go.opentelemetry.io/otel"
  "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
  "go.opentelemetry.io/otel/sdk/resource"
  sdktrace "go.opentelemetry.io/otel/sdk/trace"
  semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

func initTracer() {
  ctx := context.Background()
  exp, _ := otlptracehttp.New(ctx)
  res, _ := resource.New(ctx, resource.WithAttributes(
    semconv.ServiceName("my-service"),
    semconv.ServiceNamespace("电商主站"),
    semconv.DeploymentEnvironment("production"),
    semconv.ServiceVersion("1.0.0"),
  ))
  tp := sdktrace.NewTracerProvider(
    sdktrace.WithBatcher(exp),
    sdktrace.WithResource(res),
  )
  otel.SetTracerProvider(tp)
}
EOF

# 3. 配置上报端点后构建启动
export OTEL_EXPORTER_OTLP_ENDPOINT=${ep}
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf

go run .`}
        />
      )}
      dockerContent={(ep) => (
        <CodeBlock
          language="BASH"
          code={`docker run \\
  --name my-service \\
  -p 8080:8080 \\
  -e OTEL_EXPORTER_OTLP_ENDPOINT=${ep} \\
  -e OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \\
  -e OTEL_SERVICE_NAME=my-service \\
  -e OTEL_SERVICE_NAMESPACE=电商主站 \\
  -e OTEL_DEPLOYMENT_ENVIRONMENT=production \\
  -e OTEL_SERVICE_VERSION=1.0.0 \\
  your-image:latest`}
        />
      )}
    />
  );
}

function IntegrationDetail({
  title,
  configPanel,
  endpointMap = REGION_ENDPOINTS,
}: {
  title: string;
  configPanel: (endpoint: string) => React.ReactNode;
  endpointMap?: Record<string, string>;
}) {
  const [region, setRegion] = useState('default');
  const [orgs, setOrgs] = useState<string[]>(['Default']);
  const endpoint = endpointMap[region] ?? endpointMap.default ?? Object.values(endpointMap)[0];
  return (
    <div style={shellStyle}>
      <TopMenuBar active="integration" />
      <Content style={{ padding: 24 }}>
        <Space style={{ marginBottom: 12 }}>
          <a href={STORY_URLS.integration} style={{ color: TOKENS.textSecondary, fontSize: 13 }}>
            <ArrowLeftOutlined /> 返回接入方式总览
          </a>
        </Space>
        <div
          style={{
            ...surfaceCardStyle,
            padding: '14px 16px',
            marginBottom: 16,
          }}
        >
          <Space size={8} align="center">
            <RocketOutlined style={{ color: TOKENS.primary }} />
            <Title level={4} style={{ margin: 0 }}>
              {title}
            </Title>
            <Tag color="processing" style={{ margin: 0 }}>
              接入详情
            </Tag>
          </Space>
        </div>
        {/* ① 上报端点 */}
        <div style={{ ...surfaceCardStyle, padding: '14px 16px', marginBottom: 16 }}>
          <Space size={8} style={{ marginBottom: 4 }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 22,
                height: 22,
                borderRadius: '50%',
                background: TOKENS.primary,
                color: '#fff',
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              1
            </span>
            <Title level={5} style={{ margin: 0 }}>
              上报端点
            </Title>
          </Space>
          <div style={{ paddingLeft: 30 }}>
            <EndpointPanel
              region={region}
              setRegion={setRegion}
              orgs={orgs}
              setOrgs={setOrgs}
              endpointMap={endpointMap}
            />
          </div>
        </div>
        {/* ② 接入配置 */}
        <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
          <Space size={8} style={{ marginBottom: 4 }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 22,
                height: 22,
                borderRadius: '50%',
                background: TOKENS.primary,
                color: '#fff',
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              2
            </span>
            <Title level={5} style={{ margin: 0 }}>
              接入配置
            </Title>
          </Space>
          <div style={{ paddingLeft: 30 }}>{configPanel(endpoint)}</div>
        </div>
      </Content>
    </div>
  );
}

/* ============================================================
 * 接入列表 · 已接入实例视图
 *  1) 顶部二级导航"添加接入 / 接入列表"(二级页之间切换)
 *  2) 顶部工具栏:服务名搜索 + 接入方式 Select + 环境 Select + 时间 Radio
 *  3) 表格列:服务 / namespace / 接入方式 / 上报协议 / 接入时间 / 最近上报 / 状态 / 操作
 *  4) 状态判定复用服务目录三态(活跃 / 静默 / 已归档),不在接入列表独立计算
 *  5) 接入时间 = service.name + namespace 联合键首次 VictoriaTrace 落库时间
 * ============================================================ */

type IntegrationMethod =
  | 'Node.js'
  | 'Java'
  | 'Python'
  | '.NET'
  | 'Go'
  | 'OTC'
  | 'eBPF'
  | 'K8s';

type InstanceState = 'active' | 'silent' | 'archived';

interface IntegrationInstanceRow {
  key: string;
  service: string;
  namespace: string;
  method: IntegrationMethod;
  env: string;
  firstSeen: string;
  lastSeen: string;
  state: InstanceState;
  version: string;
}

const INSTANCES: IntegrationInstanceRow[] = [
  {
    key: 'i1',
    service: 'checkout-api',
    namespace: 'billing',
    method: 'Node.js',
    env: 'production',
    firstSeen: '3 天前',
    lastSeen: '5 分钟前',
    state: 'active',
    version: 'v3.1.3',
  },
  {
    key: 'i2',
    service: 'payment-svc',
    namespace: 'billing',
    method: 'Java',
    env: 'production',
    firstSeen: '12 天前',
    lastSeen: '2 分钟前',
    state: 'active',
    version: 'v5.2.0',
  },
  {
    key: 'i3',
    service: 'inventory-svc',
    namespace: 'billing',
    method: 'Python',
    env: 'production',
    firstSeen: '8 天前',
    lastSeen: '11 分钟前',
    state: 'active',
    version: 'v1.4.1',
  },
  {
    key: 'i4',
    service: 'auth-svc',
    namespace: 'iam',
    method: 'Go',
    env: 'production',
    firstSeen: '21 天前',
    lastSeen: '4 分钟前',
    state: 'active',
    version: 'v3.0.2',
  },
  {
    key: 'i5',
    service: 'legacy-portal',
    namespace: 'platform',
    method: '.NET',
    env: 'production',
    firstSeen: '46 天前',
    lastSeen: '1 天前',
    state: 'silent',
    version: 'v0.9.0',
  },
  {
    key: 'i6',
    service: 'api-gateway',
    namespace: 'platform',
    method: 'OTC',
    env: 'production',
    firstSeen: '60 天前',
    lastSeen: '3 分钟前',
    state: 'active',
    version: 'v2.8.0',
  },
  {
    key: 'i7',
    service: 'user-api',
    namespace: 'platform',
    method: 'Node.js',
    env: 'production',
    firstSeen: '15 天前',
    lastSeen: '7 分钟前',
    state: 'active',
    version: 'v2.5.0',
  },
  {
    key: 'i8',
    service: 'web-storefront',
    namespace: 'storefront',
    method: 'K8s',
    env: 'production',
    firstSeen: '32 天前',
    lastSeen: '6 小时前',
    state: 'silent',
    version: 'v1.7.0',
  },
  {
    key: 'i9',
    service: 'catalog-api',
    namespace: 'storefront',
    method: 'Java',
    env: 'production',
    firstSeen: '9 天前',
    lastSeen: '18 分钟前',
    state: 'active',
    version: 'v2.1.0',
  },
  {
    key: 'i10',
    service: 'obc-prod',
    namespace: 'observability',
    method: 'eBPF',
    env: 'production',
    firstSeen: '5 天前',
    lastSeen: '22 分钟前',
    state: 'active',
    version: 'v1.0.0',
  },
  {
    key: 'i11',
    service: 'auth-svc',
    namespace: 'staging-iam',
    method: 'Java',
    env: 'staging',
    firstSeen: '4 天前',
    lastSeen: '38 分钟前',
    state: 'active',
    version: 'v5.3.0-rc1',
  },
  {
    key: 'i12',
    service: 'reporting-job',
    namespace: 'billing',
    method: 'Python',
    env: 'production',
    firstSeen: '90 天前',
    lastSeen: '14 天前',
    state: 'archived',
    version: 'v0.6.0',
  },
];

/** 接入方式 Tag 颜色(SDK 用不同色区分语言,非 SDK 用另一组) */
const METHOD_TAG_STYLE: Record<IntegrationMethod, { bg: string; color: string }> = {
  'Node.js': { bg: '#10b981', color: '#fff' },
  Java: { bg: '#f59e0b', color: '#fff' },
  Python: { bg: '#3b82f6', color: '#fff' },
  '.NET': { bg: '#8b5cf6', color: '#fff' },
  Go: { bg: '#0ea5e9', color: '#fff' },
  OTC: { bg: TOKENS.primary, color: '#fff' },
  eBPF: { bg: '#64748b', color: '#fff' },
  K8s: { bg: '#0d9488', color: '#fff' },
};

const STATE_TAG: Record<InstanceState, { color: string; bg: string; label: string; dot: string }> = {
  active: { color: TOKENS.success, bg: '#e6f9f0', label: '活跃', dot: TOKENS.success },
  silent: { color: TOKENS.textSecondary, bg: '#f1f5f9', label: '静默', dot: TOKENS.textSecondary },
  archived: { color: TOKENS.warning, bg: '#fef3c7', label: '已归档', dot: TOKENS.warning },
};

function IntegrationInstanceList() {
  const [search, setSearch] = useState('');
  const [method, setMethod] = useState<'all' | IntegrationMethod>('all');
  const [env, setEnv] = useState('all');
  const [timeRange, setTimeRange] = useState('7d');

  const filtered = INSTANCES.filter((row) => {
    if (search && !`${row.service} ${row.namespace}`.toLowerCase().includes(search.toLowerCase())) return false;
    if (method !== 'all' && row.method !== method) return false;
    if (env !== 'all' && row.env !== env) return false;
    return true;
  });

  const columns: ColumnsType<IntegrationInstanceRow> = [
    {
      title: '服务',
      dataIndex: 'service',
      key: 'service',
      width: 200,
      render: (_v, row) => (
        <a
          href={STORY_URLS.service}
          style={{ color: TOKENS.text, fontWeight: 600, textDecoration: 'none' }}
        >
          {row.service}
        </a>
      ),
    },
    {
      title: '应用',
      dataIndex: 'namespace',
      key: 'namespace',
      width: 140,
      render: (v: string) => (
        <a href={STORY_URLS.service} style={{ color: TOKENS.primary, textDecoration: 'none' }}>
          {v}
        </a>
      ),
    },
    {
      title: '环境',
      dataIndex: 'env',
      key: 'env',
      width: 120,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {v}
        </Text>
      ),
    },
    {
      title: '接入方式',
      dataIndex: 'method',
      key: 'method',
      width: 120,
      render: (v: IntegrationMethod) => {
        const s = METHOD_TAG_STYLE[v];
        return (
          <Tag style={{ background: s.bg, color: s.color, border: 'none', margin: 0, fontSize: 11 }}>
            {v}
          </Tag>
        );
      },
      filters: [
        { text: 'SDK', value: 'SDK' },
        { text: 'OTC', value: 'OTC' },
        { text: 'eBPF', value: 'eBPF' },
        { text: 'K8s', value: 'K8s' },
      ],
      onFilter: () => true,
    },
    {
      title: '接入时间',
      dataIndex: 'firstSeen',
      key: 'firstSeen',
      width: 110,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {v}
        </Text>
      ),
    },
    {
      title: '最近上报',
      dataIndex: 'lastSeen',
      key: 'lastSeen',
      width: 110,
      render: (v: string, row) => {
        const isStale = row.state === 'silent' || row.state === 'archived';
        return (
          <span
            style={{
              fontSize: 12,
              color: isStale ? TOKENS.warning : TOKENS.textSecondary,
              fontWeight: isStale ? 600 : 400,
            }}
          >
            {v}
          </span>
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'state',
      key: 'state',
      width: 100,
      render: (v: InstanceState) => {
        const s = STATE_TAG[v];
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '2px 10px',
              background: s.bg,
              color: s.color,
              borderRadius: 10,
              fontSize: 12,
              fontWeight: 500,
            }}
          >
            <span
              style={{
                display: 'inline-block',
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: s.dot,
              }}
            />
            {s.label}
          </span>
        );
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: () => (
        <Button
          type="link"
          size="small"
          icon={<EyeOutlined />}
          href={STORY_URLS.service}
          style={{ padding: 0 }}
        >
          查看
        </Button>
      ),
    },
  ];

  return (
    <div style={shellStyle}>
      <TopMenuBar active="integration" />
      <IntegrationSubNav active="list" />
      <Content style={{ padding: 24 }}>
        <div
          style={{
            ...surfaceCardStyle,
            padding: '14px 16px',
            marginBottom: 16,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <Space size={8} align="center">
            <UnorderedListOutlined style={{ color: TOKENS.primary }} />
            <Title level={4} style={{ margin: 0 }}>
              接入列表
            </Title>
            <Tag style={{ margin: 0 }}>已接入 {INSTANCES.length} 个实例</Tag>
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            按「接入」维度看所有已上报数据的服务;按健康度看请到「服务」菜单
          </Text>
        </div>

        {/* 顶部工具栏 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 12,
            flexWrap: 'wrap',
          }}
        >
          <Input
            allowClear
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索服务名 / 应用"
            prefix={<SearchOutlined />}
            style={{ width: 240 }}
          />
          <Select
            value={method}
            onChange={setMethod}
            style={{ width: 160 }}
            options={[
              { value: 'all', label: '全部接入方式' },
              { value: 'Node.js', label: 'Node.js' },
              { value: 'Java', label: 'Java' },
              { value: 'Python', label: 'Python' },
              { value: '.NET', label: '.NET' },
              { value: 'Go', label: 'Go' },
              { value: 'OTC', label: 'OTC' },
              { value: 'eBPF', label: 'eBPF' },
              { value: 'K8s', label: 'K8s' },
            ]}
          />
          <Select
            value={env}
            onChange={setEnv}
            style={{ width: 140 }}
            options={[
              { value: 'all', label: '全部环境' },
              { value: 'production', label: 'production' },
              { value: 'staging', label: 'staging' },
              { value: 'dev', label: 'dev' },
            ]}
          />
          <div style={{ flex: 1 }} />
          <Radio.Group
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            size="small"
            buttonStyle="solid"
          >
            <Radio.Button value="15m">15m</Radio.Button>
            <Radio.Button value="1h">1h</Radio.Button>
            <Radio.Button value="4h">4h</Radio.Button>
            <Radio.Button value="1d">1d</Radio.Button>
            <Radio.Button value="7d">7d</Radio.Button>
          </Radio.Group>
        </div>

        <Table<IntegrationInstanceRow>
          rowKey="key"
          columns={columns}
          dataSource={filtered}
          pagination={{
            pageSize: 10,
            showSizeChanger: false,
            showTotal: (total) => `共 ${total} 条`,
          }}
          size="middle"
        />
      </Content>
    </div>
  );
}

/* ============================================================
 * 对外暴露
 *
 * 拆分自 apm-integration-pages.stories.tsx;
 * 让 add / list 两个 .stories.tsx 文件从这里 import 复用。
 * ============================================================ */
export {
  IntegrationSubNav,
  TopMenuBar,
  IntegrationCatalog,
  IntegrationDetail,
  IntegrationInstanceList,
  EndpointPanel,
  CodeBlock,
  JavaConfigPanel,
  NodeConfigPanel,
  OtcConfigPanel,
  EbpfConfigPanel,
  K8sConfigPanel,
  PythonConfigPanel,
  DotnetConfigPanel,
  GoConfigPanel,
  REGION_ENDPOINTS,
  OTC_TRACES_ENDPOINTS,
  STORY_URLS,
  TOKENS,
};
