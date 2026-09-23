'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  ApiOutlined,
  CodeOutlined,
  CoffeeOutlined,
  CopyOutlined,
  DeploymentUnitOutlined,
  DotNetOutlined,
  ExperimentOutlined,
  JavaScriptOutlined,
  KubernetesOutlined,
  PythonOutlined,
} from '@ant-design/icons';
import { Alert, Button, Drawer, Form, Input, message, Segmented, Select, Space, Tabs, Tag, Typography } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { type CatalogStateKind } from '@/app/apm/components/catalog-state';
import { getProbeCapability, type ProbeLanguage } from '@/app/apm/integration/probe-capability-matrix';
import type { ApmApplication, ApmCloudRegion, ApmIngestSnippet, ApmIngestSnippetInput } from '@/app/apm/types';
import { HandledRequestError } from '@/utils/request';
import { useTranslation } from '@/utils/i18n';

interface IntegrationMethod {
  key: string;
  title: string;
  description: string;
  icon: ReactNode;
  badge?: string;
  language?: ApmIngestSnippetInput['language'];
  available: boolean;
}

interface IntegrationMethodDef {
  key: string;
  title: string;
  icon: ReactNode;
  language?: ApmIngestSnippetInput['language'];
  available: boolean;
}

const INTEGRATION_GROUPS: { key: string; title: string; icon: ReactNode; methods: IntegrationMethodDef[] }[] = [
  {
    key: 'sdk', title: 'SDK', icon: <CodeOutlined aria-hidden="true" />, methods: [
      { key: 'nodejs', title: 'Node.js', icon: <JavaScriptOutlined aria-hidden="true" />, language: 'nodejs', available: true },
      { key: 'java', title: 'Java', icon: <CoffeeOutlined aria-hidden="true" />, language: 'java', available: true },
      { key: 'python', title: 'Python', icon: <PythonOutlined aria-hidden="true" />, language: 'python', available: true },
      { key: 'dotnet', title: '.NET', icon: <DotNetOutlined aria-hidden="true" />, language: 'dotnet', available: true },
      { key: 'go', title: 'Go', icon: <CodeOutlined aria-hidden="true" />, language: 'go', available: true },
    ],
  },
  { key: 'otel', title: 'OpenTelemetry', icon: <ApiOutlined aria-hidden="true" />, methods: [{ key: 'otel-collector', title: 'OTel Collector', icon: <DeploymentUnitOutlined aria-hidden="true" />, available: false }] },
  { key: 'ebpf', title: 'eBPF', icon: <ExperimentOutlined aria-hidden="true" />, methods: [{ key: 'ebpf-obi', title: 'eBPF', icon: <ExperimentOutlined aria-hidden="true" />, available: false }] },
  { key: 'kubernetes', title: 'Kubernetes', icon: <KubernetesOutlined aria-hidden="true" />, methods: [{ key: 'otel-operator', title: 'Kubernetes', icon: <KubernetesOutlined aria-hidden="true" />, available: false }] },
];

type PageState = 'loading' | 'empty' | 'ready' | 'error';
type SnippetMode = 'agent' | 'docker' | 'kubernetes';
type SnippetForm = Omit<ApmIngestSnippetInput, 'language' | 'runtime'>;
type CatalogSource = 'applications' | 'cloud-regions';
type Translate = (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string;

interface CatalogLoadFailure {
  source: CatalogSource;
  error: unknown;
}

interface CatalogLoadError {
  status: '403' | 'warning' | 'error';
  title: string;
  description: string;
}

function catalogLoadError(source: CatalogSource, error: unknown, t: Translate): CatalogLoadError {
  const status = error instanceof HandledRequestError ? error.status : undefined;
  if (source === 'cloud-regions') {
    if (status === 403) {
      return {
        status: '403',
        title: t('apm.integration.regionForbidden', '无权查看云区域'),
        description: t('apm.integration.regionForbiddenDesc', '请联系管理员为当前组织配置云区域查看权限。'),
      };
    }
    return {
      status: status === 503 ? 'warning' : 'error',
      title: t('apm.integration.regionUnavailable', '云区域暂不可用'),
      description: status === 503
        ? t('apm.integration.regionUnavailable503', '暂时无法加载可用于接入的云区域。请重新加载；若持续失败，请联系管理员检查云区域服务。')
        : t('apm.integration.regionLoadFailed', '云区域加载失败，请检查网络后重新加载。'),
    };
  }
  if (status === 403) {
    return {
      status: '403',
      title: t('apm.integration.appForbidden', '无权查看应用'),
      description: t('apm.integration.appForbiddenDesc', '请联系管理员为当前组织配置 APM 应用查看权限。'),
    };
  }
  return {
    status: status === 503 ? 'warning' : 'error',
    title: t('apm.integration.appUnavailable', '应用列表暂不可用'),
    description: t('apm.integration.appUnavailableDesc', '暂时无法加载可用于接入的应用，请重新加载。'),
  };
}

async function copyText(value: string) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(value);
  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  try {
    textarea.select();
    if (!document.execCommand('copy')) throw new Error('Browser copy command failed');
  } finally {
    textarea.remove();
  }
}

interface GenerationIssue {
  alertType: 'warning' | 'error';
  title: string;
  description: string;
}

function requestGenerationIssue(error: unknown, t: Translate): GenerationIssue {
  const handled = error instanceof HandledRequestError ? error : null;
  const payload = (handled?.payload ?? (error as { response?: { data?: unknown } })?.response?.data) as
    | { code?: unknown; detail?: unknown; message?: unknown }
    | undefined;
  const detail = typeof payload?.detail === 'string' ? payload.detail.trim() : '';
  const code = handled?.code ?? (typeof payload?.code === 'string' ? payload.code : '');
  const rawMessage = detail
    || (typeof payload?.message === 'string' ? payload.message.trim() : '')
    || (error instanceof Error && error.message ? error.message : '');
  if (code === 'probe_artifact_not_found' || /探针文件不存在/.test(rawMessage)) {
    return {
      alertType: 'warning',
      title: t('apm.integration.probeMissingTitle', '探针包未就绪'),
      description: t(
        'apm.integration.probeMissing',
        '主机和 Docker 接入需要从平台下载探针文件。当前环境还没有这份文件，请联系管理员完成探针初始化后再试。',
      ),
    };
  }
  if (code === 'probe_artifact_unavailable' || /探针文件暂时不可用/.test(rawMessage)) {
    return {
      alertType: 'warning',
      title: t('apm.integration.probeUnavailableTitle', '探针包暂时不可用'),
      description: t(
        'apm.integration.probeUnavailable',
        '暂时无法读取探针文件，请稍后重试。若持续失败，请联系管理员检查探针存储。',
      ),
    };
  }
  return {
    alertType: 'error',
    title: t('apm.integration.generateFailedTitle', '配置生成失败'),
    description: /没有可用的被动接收地址|云区域(?:代理|接收)地址/.test(rawMessage)
      ? t('apm.integration.noReceiver', '所选云区域没有可用的接收地址，请联系管理员检查云区域代理配置后重试。')
      : (rawMessage || t('apm.integration.generateFailed', '生成接入配置失败，请稍后重试。')),
  };
}

function snippetOperationGuide(
  language: ApmIngestSnippetInput['language'],
  mode: SnippetMode,
  t: Translate,
): string {
  const guides: Record<ApmIngestSnippetInput['language'], Record<SnippetMode, string>> = {
    nodejs: {
      agent: t('apm.integration.guideNodeHost', '在原有 Node.js 启动命令末尾追加以下内容，并重启应用。'),
      docker: t('apm.integration.guideNodeDocker', '将以下安装命令写入 Dockerfile，并用 `-e` 注入环境变量后重新构建、启动容器。'),
      kubernetes: t('apm.integration.guideNodeKubernetes', '将以下环境变量合并到应用 Pod，确保镜像已预装 Node.js 自动探针后滚动重启。'),
    },
    java: {
      agent: t('apm.integration.guideJavaHost', '在原有 Java 启动命令中加入以下内容，并重启应用。'),
      docker: t('apm.integration.guideJavaDocker', '将 Java Agent 安装命令写入 Dockerfile，通过 `JAVA_TOOL_OPTIONS` 注入后重新构建、启动容器。'),
      kubernetes: t('apm.integration.guideJavaKubernetes', '将以下环境变量（含 `JAVA_TOOL_OPTIONS`）合并到应用 Pod，确保镜像包含 Java Agent 后滚动重启。'),
    },
    python: {
      agent: t('apm.integration.guidePythonHost', '按以下脚本安装探针后，用 `opentelemetry-instrument` 包装原有 Python 启动命令并重启应用。'),
      docker: t('apm.integration.guidePythonDocker', '将探针安装命令写入 Dockerfile，用 `-e` 注入环境变量并以 `opentelemetry-instrument` 启动容器。'),
      kubernetes: t('apm.integration.guidePythonKubernetes', '将以下环境变量合并到应用 Pod，确保镜像以 `opentelemetry-instrument` 启动后滚动重启。'),
    },
    dotnet: {
      agent: t('apm.integration.guideDotnetHost', '按以下脚本安装自动探针并导出环境变量后，用原有 `dotnet` 启动命令重启应用。'),
      docker: t('apm.integration.guideDotnetDocker', '将自动探针安装进镜像，用 `-e` 注入 CLR 分析器环境变量后重新构建、启动容器。'),
      kubernetes: t('apm.integration.guideDotnetKubernetes', '将以下环境变量合并到应用 Pod，确保镜像包含 .NET 自动探针后滚动重启。'),
    },
    go: {
      agent: t('apm.integration.guideGoHost', '按以下指南审阅 OpenTelemetry Go SDK 示例，接入应用代码后重新编译并重启。'),
      docker: t('apm.integration.guideGoDocker', '将 SDK 依赖安装进镜像，完成 Go SDK 初始化后重新构建、启动容器。'),
      kubernetes: t('apm.integration.guideGoKubernetes', '将以下环境变量合并到应用 Pod；应用二进制需先完成 OpenTelemetry Go SDK 初始化，然后滚动重启。'),
    },
  };
  return guides[language][mode];
}

function CapabilityTagList({ items }: { items: readonly string[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <Tag key={item}>{item}</Tag>
      ))}
    </div>
  );
}

function ProbeCapabilityPane({
  language,
  kind,
  t,
}: {
  language: ProbeLanguage;
  kind: 'frameworks' | 'discovery';
  t: Translate;
}) {
  const capability = getProbeCapability(language);
  const items = kind === 'frameworks' ? capability.frameworks : capability.inferredComponents;
  return (
    <div className="flex flex-col gap-3 pt-1">
      <Typography.Text type="secondary" className="text-xs">
        {t('apm.integration.probeVersion', '探针版本 {version}', { version: capability.version })}
      </Typography.Text>
      {kind === 'frameworks' && capability.manualInstrumentation ? (
        <Alert
          showIcon
          type="info"
          message={t('apm.integration.manualFrameworkHint', '该语言需在代码中加入对应 contrib 插桩；下列为精选常见框架。')}
        />
      ) : null}
      <Typography.Paragraph type="secondary" className="!mb-0 text-xs">
        {kind === 'frameworks'
          ? t('apm.integration.frameworksHint', '以下为当前钉死探针版本精选支持的 Web / RPC 框架，不是完整 instrumentation 清单。')
          : t('apm.integration.discoveryHint', '以下类型会在该探针打出 Client Span 后，出现在应用详情拓扑上，作为推断下游。')}
      </Typography.Paragraph>
      <CapabilityTagList items={items} />
      {kind === 'discovery' ? (
        <Typography.Paragraph type="secondary" className="!mb-0 text-xs">
          {t('apm.integration.discoveryFooter', '这是应用详情拓扑上的推断节点，不是 CMDB 或监控自动发现，也不会进入服务目录或应用列表。给 Web 服务装探针后，mysql 不会作为独立应用出现。')}
        </Typography.Paragraph>
      ) : null}
    </div>
  );
}

export default function ApmIntegrationAddPage() {
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const [messageApi, messageContextHolder] = message.useMessage();
  const { getApplications, getCloudRegions, getIngestSnippet, isLoading } = useApmApi();
  const [applications, setApplications] = useState<ApmApplication[]>([]);
  const [cloudRegions, setCloudRegions] = useState<ApmCloudRegion[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [catalogError, setCatalogError] = useState<CatalogLoadError | null>(null);
  const [emptyReason, setEmptyReason] = useState<'no-app' | 'no-region'>('no-app');
  const [selectedMethod, setSelectedMethod] = useState<IntegrationMethod | null>(null);
  const [mode, setMode] = useState<SnippetMode>('agent');
  const [snippet, setSnippet] = useState<ApmIngestSnippet | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<GenerationIssue | null>(null);
  const [form] = Form.useForm<SnippetForm>();
  const formValues = Form.useWatch([], form);
  const requestSequence = useRef(0);

  const integrationGroups = useMemo(() => {
    const copy: Record<string, { description: string; badge?: string; title?: string }> = {
      nodejs: {
        description: t('apm.integration.nodejsDesc', '自动探针，支持 Express / Nest / Koa / Fastify'),
        badge: t('apm.integration.recommended', '推荐'),
      },
      java: {
        description: t('apm.integration.javaDesc', '自动探针，支持 Spring / Dubbo / gRPC'),
        badge: t('apm.integration.recommended', '推荐'),
      },
      python: {
        description: t('apm.integration.pythonDesc', '自动探针，支持 Django / Flask / FastAPI'),
      },
      dotnet: {
        description: t('apm.integration.dotnetDesc', '自动探针，支持 Linux x86_64 glibc'),
      },
      go: {
        description: t('apm.integration.goDesc', '手动接入，生成 OpenTelemetry Provider 示例'),
        badge: t('apm.integration.manualSdk', '手动 SDK'),
      },
      'otel-collector': {
        description: t('apm.integration.otelDesc', '转发自建 Collector 链路到平台 OTLP 端点'),
      },
      'ebpf-obi': {
        title: t('apm.integration.ebpfTitle', 'eBPF 自动注入（OBI）'),
        description: t('apm.integration.ebpfDesc', '内核态自动采集服务链路'),
        badge: t('apm.integration.lowIntrusion', '低侵入'),
      },
      'otel-operator': {
        title: t('apm.integration.k8sTitle', 'Kubernetes 自动注入'),
        description: t('apm.integration.k8sDesc', 'OTel Operator 注解注入，自动接入集群服务'),
      },
    };
    return INTEGRATION_GROUPS.map((group) => ({
      ...group,
      methods: group.methods.map((method) => ({
        ...method,
        title: copy[method.key]?.title ?? method.title,
        description: copy[method.key]?.description ?? '',
        badge: copy[method.key]?.badge,
      })),
    }));
  }, [t]);

  const loadCatalog = useCallback(async () => {
    if (isLoading) return;
    setState('loading');
    setCatalogError(null);
    try {
      const requestConfig = { suppressErrorNotification: true };
      const [items, regions] = await Promise.all([
        getApplications(requestConfig).catch((error) => Promise.reject({
          source: 'applications',
          error,
        } satisfies CatalogLoadFailure)),
        getCloudRegions(requestConfig).catch((error) => Promise.reject({
          source: 'cloud-regions',
          error,
        } satisfies CatalogLoadFailure)),
      ]);
      setApplications(items.filter((item) => !item.is_builtin));
      setCloudRegions(regions);
      if (!items.some((item) => !item.is_builtin)) {
        setEmptyReason('no-app');
        setState('empty');
      } else if (regions.length === 0) {
        setEmptyReason('no-region');
        setState('empty');
      } else {
        setState('ready');
      }
    } catch (failure) {
      const normalized = failure as Partial<CatalogLoadFailure>;
      setCatalogError(catalogLoadError(
        normalized.source === 'applications' ? 'applications' : 'cloud-regions',
        normalized.error ?? failure,
        t
      ));
      setState('error');
    }
  }, [getApplications, getCloudRegions, isLoading, t]);

  useEffect(() => { void loadCatalog(); }, [loadCatalog]);

  const applicationOptions = useMemo(() => applications.map((application) => ({
    value: application.application_id,
    label: t('apm.instances.appLabel', '{name}（{id}）', { name: application.name, id: application.application_id }),
  })), [applications, t]);
  const preferredApplicationId = useMemo(() => {
    const requested = searchParams?.get('application_id') ?? null;
    return applications.some((application) => application.application_id === requested)
      ? requested ?? applications[0]?.application_id
      : applications[0]?.application_id;
  }, [applications, searchParams]);
  const cloudRegionOptions = useMemo(() => cloudRegions.map((region) => ({
    value: region.id,
    label: region.name,
  })), [cloudRegions]);
  const isGo = selectedMethod?.language === 'go';
  const generatedSnippetLabel = mode === 'kubernetes'
    ? t('apm.integration.k8sSnippet', 'Kubernetes 配置片段')
    : isGo ? t('apm.integration.goGuide', 'Go SDK 接入指南') : t('apm.integration.shellSnippet', 'Shell 接入片段');

  const openMethod = (method: IntegrationMethod) => {
    if (!method.available || !method.language) return;
    setSelectedMethod(method);
    setMode('agent');
    setSnippet(null);
    setGenerationError(null);
  };

  const copyWithFeedback = async (value: string, success: string) => {
    try {
      await copyText(value);
      messageApi.success(success);
    } catch {
      messageApi.error(t('apm.integration.copyFailure', '复制失败，请手动选择并复制'));
    }
  };

  const generate = useCallback(async (values: SnippetForm) => {
    if (!selectedMethod?.language) return;
    const sequence = ++requestSequence.current;
    setGenerating(true);
    setGenerationError(null);
    try {
      const result = await getIngestSnippet({
        ...values,
        language: selectedMethod.language,
        runtime: mode === 'agent' ? 'host' : mode,
      });
      if (sequence !== requestSequence.current) return;
      setSnippet(result);
    } catch (error) {
      if (sequence !== requestSequence.current) return;
      setSnippet(null);
      setGenerationError(requestGenerationIssue(error, t));
    } finally {
      if (sequence === requestSequence.current) setGenerating(false);
    }
  }, [getIngestSnippet, mode, selectedMethod?.language, t]);

  const watchedFormKey = JSON.stringify(formValues ?? {});
  useEffect(() => {
    if (!selectedMethod?.language) return;
    const timer = window.setTimeout(() => {
      void form.validateFields({ validateOnly: true })
        .then((values) => generate(values))
        .catch(() => undefined);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [form, generate, mode, selectedMethod?.language, watchedFormKey]);

  return (
    <ApmRouteShell title={t('apm.integration.title', '添加接入')} description={t('apm.integration.description', '选择语言与应用，即时生成可复制的 OpenTelemetry 接入配置。')}>
      {messageContextHolder}
      {state === 'loading' ? (
        <ApmSurface><CatalogState kind="loading" /></ApmSurface>
      ) : state === 'error' && catalogError ? (
        <ApmSurface>
          <CatalogState
            kind={(catalogError.status === '403'
              ? 'forbidden'
              : catalogError.status === 'warning' ? 'degraded' : 'error') satisfies CatalogStateKind}
            title={catalogError.title}
            description={catalogError.description}
            onRetry={catalogError.status === '403' ? undefined : () => void loadCatalog()}
          />
        </ApmSurface>
      ) : state === 'empty' ? (
        <ApmSurface>
          <CatalogState
            kind="empty"
            description={emptyReason === 'no-app'
              ? t('apm.integration.createAppFirst', '请先创建一个应用，再生成接入配置。')
              : t('apm.integration.noRegion', '暂无可用云区域，请联系管理员检查云区域配置。')}
            action={applications.length === 0 ? (
              <Link href="/apm/integration/applications"><Button type="primary">{t('apm.integration.goToApplications', '前往应用管理')}</Button></Link>
            ) : (
              <Button type="primary" onClick={() => void loadCatalog()}>{t('apm.common.reload', '重新加载')}</Button>
            )}
          />
        </ApmSurface>
      ) : (
        <div className="flex flex-col gap-4">
          {integrationGroups.map((group) => (
            <ApmSurface key={group.key}>
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--color-text-1)]"><span className="text-[var(--color-primary)]">{group.icon}</span>{group.title}</div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {group.methods.map((method) => (
                  <button
                    key={method.key}
                    aria-label={method.available
                      ? t('apm.integration.methodAria', '{title} 接入', { title: method.title })
                      : t('apm.integration.methodAriaClosed', '{title} 接入，规划中', { title: method.title })}
                    className="min-h-32 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4 text-left transition-colors duration-150 enabled:cursor-pointer enabled:hover:border-[var(--color-primary)] enabled:hover:bg-[var(--color-fill-1)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!method.available}
                    title={method.available
                      ? t('apm.integration.selectMethod', '选择 {title} 接入', { title: method.title })
                      : t('apm.integration.methodClosed', '{title} 接入规划中', { title: method.title })}
                    type="button"
                    onClick={() => openMethod(method)}
                  >
                    <div className="flex min-h-24 items-start justify-between gap-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--color-primary-bg-active)] text-base text-[var(--color-primary)]">
                          {method.icon}
                        </span>
                        <div className="min-w-0">
                          <Typography.Title level={5} className="!mb-2 !text-sm">{method.title}</Typography.Title>
                          <Typography.Text type="secondary" className="text-xs leading-5">{method.description}</Typography.Text>
                        </div>
                      </div>
                      <Space direction="vertical" align="end" size={4}>{method.badge ? <Tag color="blue">{method.badge}</Tag> : null}{!method.available ? <Tag>{t('apm.integration.planned', '规划中')}</Tag> : null}</Space>
                    </div>
                  </button>
                ))}
              </div>
            </ApmSurface>
          ))}
        </div>
      )}

      <Drawer
        destroyOnHidden
        open={Boolean(selectedMethod)}
        placement="right"
        title={t('apm.integration.drawerTitle', '{title} 接入', { title: selectedMethod?.title ?? '' })}
        width="min(960px, 100vw)"
        styles={{ body: { overflowY: 'auto' } }}
        onClose={() => setSelectedMethod(null)}
      >
        <Tabs
          defaultActiveKey="guide"
          items={[
            {
              key: 'guide',
              label: t('apm.integration.tabGuide', '接入指引'),
              children: (
        <div className="flex flex-col gap-4 pt-2">
          <div className="rounded-lg bg-[var(--color-fill-1)] p-4">
            <div className="mb-1 flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-full bg-[var(--color-primary)] text-sm font-semibold text-[var(--color-primary-foreground)]">1</span><Typography.Text strong>{t('apm.integration.configTitle', '接入配置')}</Typography.Text></div>
            <Typography.Text type="secondary" className="mb-4 block text-xs">{t('apm.integration.configHint', '应用 ID、服务名称和版本将映射到标准 OpenTelemetry 资源属性；平台根据所选云区域分配上报端点。')}</Typography.Text>
            <Form<SnippetForm>
              form={form}
              key={`${selectedMethod?.key ?? 'integration-form'}:${preferredApplicationId ?? ''}`}
              layout="vertical"
              initialValues={{
                application_id: preferredApplicationId,
                cloud_region_id: cloudRegions[0]?.id,
                service_name: '',
                service_version: '',
                environment: 'production',
                sample_rate: 100,
              }}
              onValuesChange={() => {
                setSnippet(null);
                setGenerationError(null);
              }}
            >
              <div className="grid gap-x-5 md:grid-cols-2">
                <Form.Item name="application_id" label={t('apm.integration.application', '应用')} rules={[{ required: true, message: t('apm.integration.applicationRequired', '请选择应用') }]}><Select showSearch optionFilterProp="label" options={applicationOptions} /></Form.Item>
                <Form.Item name="cloud_region_id" label={t('apm.integration.cloudRegion', '云区域')} rules={[{ required: true, message: t('apm.integration.cloudRegionRequired', '请选择云区域') }]}><Select showSearch optionFilterProp="label" options={cloudRegionOptions} /></Form.Item>
                <Form.Item name="service_name" label={t('apm.integration.serviceName', '服务名称')} rules={[{ required: true, whitespace: true, message: t('apm.integration.serviceNameRequired', '请输入服务名称') }, { max: 256 }]}><Input placeholder={t('apm.integration.serviceNamePlaceholder', 'service.name，例如 checkout')} /></Form.Item>
                <Form.Item name="service_version" label={t('apm.integration.serviceVersion', '服务版本')} rules={[{ max: 256 }]}><Input placeholder={t('apm.integration.serviceVersionPlaceholder', 'service.version，例如 1.4.0（可选）')} /></Form.Item>
                <Form.Item name="environment" label={t('apm.integration.deployEnv', '部署环境')} rules={[{ required: true, whitespace: true, message: t('apm.integration.deployEnvRequired', '请输入部署环境') }, { max: 256 }]}><Input placeholder={t('apm.integration.deployEnvPlaceholder', 'deployment.environment，例如 production')} /></Form.Item>
                <Form.Item name="sample_rate" label={t('apm.integration.sampleRate', '采样率')} rules={[{ required: true, message: t('apm.integration.sampleRateRequired', '请选择采样率') }]}>
                  <Select
                    options={[100, 50, 20, 10, 5, 1].map((value) => ({
                      value,
                      label: `${value}%`,
                    }))}
                  />
                </Form.Item>
              </div>
              <Form.Item label={t('apm.integration.runtime', '运行方式')} className="!mb-4">
                <Segmented
                  aria-label={t('apm.integration.runtime', '运行方式')}
                  value={mode}
                  onChange={(value) => { setMode(value as SnippetMode); setSnippet(null); setGenerationError(null); }}
                  options={[
                    { label: isGo ? t('apm.integration.goManual', 'Go 手动 SDK') : t('apm.integration.autoProbe', '{title} 自动探针', { title: selectedMethod?.title ?? '' }), value: 'agent' },
                    { label: t('apm.integration.dockerRuntime', 'Docker 运行（-e 注入）'), value: 'docker' },
                    { label: t('apm.integration.k8sPod', 'Kubernetes Pod（Downward API）'), value: 'kubernetes' },
                  ]}
                />
              </Form.Item>
              {generationError ? (
                <Alert
                  className="mb-4"
                  showIcon
                  type={generationError.alertType}
                  message={generationError.title}
                  description={generationError.description}
                  action={<Button size="small" onClick={() => void form.validateFields().then(generate)}>{t('common.retry', '重试')}</Button>}
                />
              ) : generating ? <Typography.Text type="secondary">{t('apm.integration.generating', '正在自动生成配置…')}</Typography.Text> : null}
            </Form>
          </div>

          {snippet ? (
            <div className="rounded-lg bg-[var(--color-fill-1)] p-4">
              <div className="mb-4 flex items-center gap-2">
                <span className="grid h-7 w-7 place-items-center rounded-full bg-[var(--color-primary)] text-sm font-semibold text-[var(--color-primary-foreground)]">2</span>
                <Typography.Text strong>{t('apm.integration.resultTitle', '生成结果')}</Typography.Text>
              </div>
              <div>
                <Typography.Text type="secondary" className="mb-1 block text-xs">{t('apm.integration.otlpHttpEndpoint', 'OTLP/HTTP 上报端点')}</Typography.Text>
                <Space.Compact block>
                  <Button disabled>POST</Button>
                  <Input readOnly value={snippet.http_endpoint} />
                  <Button
                    aria-label={t('apm.integration.copyEndpoint', '复制 HTTP 上报端点')}
                    icon={<CopyOutlined aria-hidden />}
                    onClick={() => void copyWithFeedback(
                      snippet.http_endpoint,
                      t('apm.integration.copyEndpointSuccess', 'HTTP 上报端点已复制')
                    )}
                  >{t('common.copy', '复制')}</Button>
                </Space.Compact>
                <Typography.Text type="secondary" className="mt-2 block text-xs">{t('apm.integration.otlpHttpHint', '平台使用所选云区域的被动接收地址，固定通过 OTLP/HTTP（http/protobuf）上报。')}</Typography.Text>
              </div>
              <div className="mt-4 border-t border-[var(--color-border)] pt-4">
                <div role="group" aria-labelledby="apm-shell-snippet-title" className="mb-2 flex items-center justify-between gap-3">
                  <Typography.Text id="apm-shell-snippet-title" strong>{generatedSnippetLabel}</Typography.Text>
                  <Button
                    aria-label={isGo && mode !== 'kubernetes'
                      ? t('apm.integration.copyGoGuide', '复制 Go SDK 接入指南')
                      : mode === 'kubernetes'
                        ? t('apm.integration.copyK8s', '复制 Kubernetes 配置片段')
                        : t('apm.integration.copyShellSnippet', '复制 Shell 接入片段')}
                    icon={<CopyOutlined aria-hidden />}
                    onClick={() => void copyWithFeedback(
                      snippet.code,
                      t('apm.integration.copied', '{label}已复制', { label: generatedSnippetLabel })
                    )}
                  >{t('apm.integration.copySnippet', '复制片段')}</Button>
                </div>
                <pre className="max-h-[420px] overflow-auto rounded-lg border border-[var(--color-code-block-border)] bg-[var(--color-code-block-bg)] p-4 font-mono text-sm leading-6 text-[var(--color-code-block-text)]"><code>{snippet.code}</code></pre>
                {selectedMethod?.language ? (
                  <Typography.Text className="mt-2 block text-sm text-[var(--color-text-2)]">
                    {snippetOperationGuide(selectedMethod.language, mode, t)}
                  </Typography.Text>
                ) : null}
                <Typography.Text type="secondary" className="mt-1 block text-xs">
                  {t('apm.integration.instanceIdentityHelp', '实例 ID 在应用进程启动时生成，每个副本唯一。')}
                </Typography.Text>
              </div>
            </div>
          ) : null}
        </div>
              ),
            },
            {
              key: 'frameworks',
              label: t('apm.integration.tabFrameworks', '支持框架'),
              children: selectedMethod?.language ? (
                <ProbeCapabilityPane language={selectedMethod.language} kind="frameworks" t={t} />
              ) : null,
            },
            {
              key: 'discovery',
              label: t('apm.integration.tabDiscovery', '发现能力'),
              children: selectedMethod?.language ? (
                <ProbeCapabilityPane language={selectedMethod.language} kind="discovery" t={t} />
              ) : null,
            },
          ]}
        />
      </Drawer>
    </ApmRouteShell>
  );
}
