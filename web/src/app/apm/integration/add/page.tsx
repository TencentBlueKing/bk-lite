'use client';

import Link from 'next/link';
import {
  CheckCircleOutlined,
  CodeOutlined,
  DeploymentUnitOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { Alert, Button, Tag, Typography } from 'antd';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';

const RUNTIMES = [
  { name: 'Node.js', badge: 'JS', description: '零代码自动探针，支持 Express、Nest、Koa 与 Fastify。', tag: '自动探针' },
  { name: 'Java', badge: 'JV', description: '字节码注入接入，支持 Spring、Dubbo 与 gRPC。', tag: '自动探针' },
  { name: 'Python', badge: 'PY', description: '运行时 SDK 接入，支持 Django、Flask 与 FastAPI。', tag: 'SDK' },
  { name: '.NET', badge: '.N', description: '基于 OpenTelemetry .NET 自动探针采集链路。', tag: '自动探针' },
  { name: 'Go', badge: 'GO', description: '编译期引入 OpenTelemetry SDK，在关键调用处埋点。', tag: 'SDK' },
] as const;

const INFRASTRUCTURE = [
  { name: 'OTel Collector', badge: 'OT', description: '复用已有 Collector，通过 exporter 将链路发送到平台。', tag: 'Collector' },
  { name: 'Kubernetes', badge: 'K8', description: '通过 OTel Operator 为工作负载动态注入探针与实例身份。', tag: 'Operator' },
] as const;

interface RuntimeCardProps {
  name: string;
  badge: string;
  description: string;
  tag: string;
}

function RuntimeCard({ name, badge, description, tag }: RuntimeCardProps) {
  return (
    <article className="flex min-h-36 flex-col rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4 transition-colors duration-200 hover:border-[var(--color-primary)]">
      <div className="flex items-start justify-between gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[var(--color-primary-bg-active)] text-xs font-semibold text-[var(--color-primary)]">
          {badge}
        </span>
        <Tag bordered={false}>{tag}</Tag>
      </div>
      <Typography.Title level={3} className="!mb-1 !mt-3 !text-sm !font-semibold">
        {name}
      </Typography.Title>
      <Typography.Text type="secondary" className="text-xs leading-5">
        {description}
      </Typography.Text>
      <div className="mt-auto flex items-center gap-1 pt-3 text-xs text-[var(--color-success)]">
        <CheckCircleOutlined aria-hidden="true" />
        支持受控 OTLP 接入
      </div>
    </article>
  );
}

export default function ApmIntegrationAddPage() {
  return (
    <ApmRouteShell
      title="添加 APM 接入"
      description="创建受控 OTLP 接入源，并生成包含鉴权与动态实例身份的接入配置。"
    >
      <div className="flex flex-col gap-4">
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <Typography.Text strong className="block text-sm">接入方式总览</Typography.Text>
              <Typography.Text type="secondary" className="text-xs">
                按运行环境选择探针；所有方式最终统一发送到受控 OTLP Gateway。
              </Typography.Text>
            </div>
            <Link href="/apm/integration/instances">
              <Button icon={<UnorderedListOutlined aria-hidden="true" />}>查看接入实例</Button>
            </Link>
          </div>
        </ApmSurface>

        <section aria-labelledby="apm-sdk-title">
          <div className="mb-3 flex items-center gap-2">
            <CodeOutlined className="text-[var(--color-primary)]" aria-hidden="true" />
            <Typography.Text strong id="apm-sdk-title">应用 SDK</Typography.Text>
            <Tag bordered={false}>{RUNTIMES.length} 种</Tag>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
            {RUNTIMES.map((runtime) => <RuntimeCard key={runtime.name} {...runtime} />)}
          </div>
        </section>

        <section aria-labelledby="apm-infrastructure-title">
          <div className="mb-3 flex items-center gap-2">
            <DeploymentUnitOutlined className="text-[var(--color-primary)]" aria-hidden="true" />
            <Typography.Text strong id="apm-infrastructure-title">基础设施</Typography.Text>
            <Tag bordered={false}>{INFRASTRUCTURE.length} 种</Tag>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
            {INFRASTRUCTURE.map((runtime) => <RuntimeCard key={runtime.name} {...runtime} />)}
          </div>
        </section>

        <Alert
          type="info"
          showIcon
          message="接入凭证只在创建或轮换成功时展示一次；实例 ID 必须按 Pod、容器或主机动态生成，不能在多个副本间复用。"
        />
      </div>
    </ApmRouteShell>
  );
}
