import ApmRouteShell from '@/app/apm/components/apm-route-shell';

export default function ApmIntegrationAddPage() {
  return (
    <ApmRouteShell
      title="添加 APM 接入"
      description="创建受控 OTLP 接入源，并生成包含鉴权与动态实例身份的接入配置。"
    />
  );
}
