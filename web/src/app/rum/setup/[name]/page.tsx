'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  BarChartOutlined,
  EditOutlined,
} from '@ant-design/icons';
import { Button, Empty, Input, Popconfirm, Switch, Tooltip } from 'antd';

import {
  useRumQueries,
  type RumApplicationView,
  type RumSnippetSet,
} from '@/app/rum/api';
import {
  BudgetFields,
  budgetFormFromApi,
  budgetPayload,
  type BudgetForm,
} from '@/app/rum/applications/ui/budget-fields';
import KeyPanel from '@/app/rum/applications/ui/key-panel';
import { OriginChips, OriginEditor } from '@/app/rum/applications/ui/origin-editor';
import SelfCheck from '@/app/rum/applications/ui/self-check';
import SetupStep, { type SetupStepState } from '@/app/rum/applications/ui/setup-step';
import SnippetTabs from '@/app/rum/applications/ui/snippet-tabs';
import { RumDetailTitle } from '@/app/rum/components/rum-back-button';
import RumPermission from '@/app/rum/components/rum-permission';
import RumRefreshButton from '@/app/rum/components/rum-refresh-button';
import { RumCodeSkeleton, RumSetupSkeleton } from '@/app/rum/components/rum-skeleton';
import { rumErrorMessage } from '@/app/rum/lib/error-message';
import { rumIngestStatus } from '@/app/rum/lib/ingest';
import { rumBrowserEndpoints } from '@/app/rum/lib/public-endpoints';
import SemanticBadge from '@/components/semantic-badge';
import { toneSemanticPalette } from '@/app/rum/lib/cwv';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { useTranslation } from '@/utils/i18n';

export default function ApplicationSetupPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useParams<{ name: string }>();
  const name = decodeURIComponent(params.name || '');
  const {
    getApplication,
    getMeta,
    updateApplication,
    disableApplication,
    reissueKey,
    buildSnippets,
    authReady,
  } = useRumQueries();

  const [app, setApp] = useState<RumApplicationView | null>(null);
  const [origins, setOrigins] = useState<string[]>([]);
  const [originsEditing, setOriginsEditing] = useState(false);
  const [budgetForm, setBudgetForm] = useState<BudgetForm>(() => budgetFormFromApi());
  const [budgetsEditing, setBudgetsEditing] = useState(false);
  const [budgetError, setBudgetError] = useState('');
  const [reissuePending, setReissuePending] = useState(false);
  const [freshKey, setFreshKey] = useState(false);
  const [acting, setActing] = useState(false);
  const [pending, setPending] = useState(true);

  const [environment, setEnvironment] = useState('production');
  const [release, setRelease] = useState('');
  const [replayEnabled, setReplayEnabled] = useState(false);
  const [snippets, setSnippets] = useState<RumSnippetSet | null>(null);
  const [snippetError, setSnippetError] = useState('');
  const [collectUrl, setCollectUrl] = useState('');
  const [replayUrl, setReplayUrl] = useState('');
  const [sdkCdnUrl, setSdkCdnUrl] = useState('');

  const load = useCallback(async () => {
    if (!name) return;
    setPending(true);
    try {
      const view = await getApplication(name);
      setApp(view);
      setOrigins(view.origins?.slice() || []);
      setOriginsEditing(false);
      setBudgetForm(budgetFormFromApi(view.budgets));
      setBudgetsEditing(false);
      setFreshKey(false);
    } catch {
      setApp(null);
    } finally {
      setPending(false);
    }
  }, [getApplication, name]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      if (!name) return;
      setPending(true);
      void getApplication(name)
        .then((view) => {
          if (isCancelled()) return;
          setApp(view);
          setOrigins(view.origins?.slice() || []);
          setOriginsEditing(false);
          setBudgetForm(budgetFormFromApi(view.budgets));
          setBudgetsEditing(false);
          setFreshKey(false);
        })
        .catch(() => {
          if (!isCancelled()) setApp(null);
        })
        .finally(() => {
          if (!isCancelled()) setPending(false);
        });
    },
    [getApplication, name],
  );

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      void getMeta()
        .then((meta) => {
          if (isCancelled()) return;
          const endpoints = rumBrowserEndpoints(
            window.location.origin,
            meta.publicOrigin,
          );
          setCollectUrl(endpoints.collectUrl);
          setReplayUrl(endpoints.replayUrl);
          setSdkCdnUrl(endpoints.sdkCdnUrl);
        })
        .catch(() => {
          if (isCancelled()) return;
          const endpoints = rumBrowserEndpoints(window.location.origin);
          setCollectUrl(endpoints.collectUrl);
          setReplayUrl(endpoints.replayUrl);
          setSdkCdnUrl(endpoints.sdkCdnUrl);
        });
    },
    [getMeta],
  );

  useEffect(() => {
    const key = app?.browserKeys?.[0];
    if (!key || !collectUrl || !replayUrl) return;
    let cancelled = false;
    void buildSnippets({
      application: app.application,
      environment,
      release,
      browserKey: key,
      collectUrl,
      replayUrl,
      sdkCdnUrl: sdkCdnUrl || undefined,
      replay: replayEnabled ? { enabled: true } : { enabled: false, samplingRate: 0 },
    })
      .then((set) => {
        if (!cancelled) {
          setSnippets(set);
          setSnippetError('');
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setSnippets(null);
          setSnippetError(rumErrorMessage(err, t));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [app, environment, release, replayEnabled, collectUrl, replayUrl, sdkCdnUrl, buildSnippets, t]);

  const saveOrigins = useCallback(async () => {
    if (!app) return;
    setActing(true);
    try {
      const view = await updateApplication(app.application, {
        origins: origins.map((value) => value.trim()).filter(Boolean),
      });
      setApp(view);
      setOrigins(view.origins?.slice() || []);
      setOriginsEditing(false);
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setActing(false);
    }
  }, [app, origins, updateApplication, t]);

  const saveBudgets = useCallback(async () => {
    if (!app) return;
    const payload = budgetPayload(budgetForm);
    if (payload === 'order') {
      setBudgetError(t('rum.budgets.order', '解压上限不能小于压缩上限'));
      return;
    }
    if (payload === 'incomplete') {
      setBudgetError(t('rum.budgets.required', '请填写完整的每分钟预算'));
      return;
    }
    setBudgetError('');
    setActing(true);
    try {
      const view = await updateApplication(app.application, { budgets: payload });
      setApp(view);
      setBudgetForm(budgetFormFromApi(view.budgets));
      setBudgetsEditing(false);
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setActing(false);
    }
  }, [app, budgetForm, t, updateApplication]);

  const toggleEnabled = useCallback(async () => {
    if (!app) return;
    setActing(true);
    try {
      const view = app.enabled
        ? await disableApplication(app.application)
        : await updateApplication(app.application, { enabled: true });
      setApp(view);
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setActing(false);
    }
  }, [app, disableApplication, updateApplication, t]);

  const reissue = useCallback(async () => {
    if (!app) return;
    setReissuePending(true);
    try {
      const view = await reissueKey(app.application);
      setApp(view);
      setFreshKey(true);
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setReissuePending(false);
    }
  }, [app, reissueKey, t]);

  const hasKey = Boolean(app?.browserKeys?.[0]);
  const snippetReady = Boolean(snippets);
  const projectionPending = Boolean(app?.projectionPending);
  const connected = app != null && !projectionPending && rumIngestStatus(app) === 'connected';
  const busy = pending || acting;

  const stepApp: SetupStepState = 'complete';
  const stepKey: SetupStepState = hasKey ? 'complete' : 'active';
  const stepInstall: SetupStepState = !hasKey ? 'pending' : snippetReady ? 'complete' : 'active';
  const stepVerify: SetupStepState = connected
    ? 'complete'
    : !app?.enabled
      ? 'danger'
      : snippetReady
        ? 'active'
        : 'pending';

  const headerVerdict = !app
    ? null
    : !app.enabled
      ? 'disabled'
      : connected
        ? 'connected'
        : !hasKey
          ? 'setup'
          : 'waiting';

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-y-auto">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <RumDetailTitle
            title={name}
            onBack={() => router.push('/rum/setup')}
            afterTitle={
              headerVerdict ? (
                <SemanticBadge
                  label={t(`rum.verdict.${headerVerdict}`)}
                  {...toneSemanticPalette(
                    headerVerdict === 'connected'
                      ? 'success'
                      : headerVerdict === 'waiting'
                        ? 'info'
                        : 'neutral',
                  )}
                />
              ) : null
            }
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            icon={<BarChartOutlined />}
            onClick={() => router.push(`/rum/applications/${encodeURIComponent(name)}/overview`)}
          >
            {t('rum.overview.title', '总览')}
          </Button>
          <RumRefreshButton onClick={() => void load()} />
          {app ? (
            <RumPermission resource="applications" action="Operate">
              <Popconfirm
                title={app.enabled ? t('rum.detail.disable', '禁用') : t('rum.detail.enable', '启用')}
                description={
                  app.enabled
                    ? t('rum.detail.disableConfirm', '确认禁用？准入将立即拒绝该应用的所有上报。')
                    : t('rum.detail.enableConfirm', '确认启用该应用？')
                }
                onConfirm={() => void toggleEnabled()}
                okText={app.enabled ? t('rum.detail.disable', '禁用') : t('rum.detail.enable', '启用')}
                cancelText={t('rum.common.cancel', '取消')}
                okButtonProps={{ danger: app.enabled }}
              >
                <Button disabled={busy}>
                  {app.enabled ? t('rum.detail.disable', '禁用') : t('rum.detail.enable', '启用')}
                </Button>
              </Popconfirm>
            </RumPermission>
          ) : null}
        </div>
      </div>

      {pending && !app ? <RumSetupSkeleton /> : null}

      {!pending && !app ? (
        <Empty
          description={
            <div className="flex flex-col gap-1">
              <span>{t('rum.detail.missing', '无法加载该应用')}</span>
              <span className="text-xs text-[var(--color-text-3)]">
                {t('rum.common.notFound', '应用不存在')}
              </span>
            </div>
          }
        />
      ) : null}

      {app ? (
        <div className="flex min-w-0 flex-col gap-6">
          <ol className="w-full list-none space-y-0 p-0">
            <SetupStep n={1} title={t('rum.detail.stepApp', '应用与 Origin')} state={stepApp}>
              <div className="space-y-2">
                <div className="flex min-w-0 flex-wrap items-baseline gap-2">
                  <span className="text-sm font-medium">
                    {t('rum.detail.originsTitle', '允许的 Origin')}
                  </span>
                  <span className="text-xs tracking-wide text-[var(--color-text-3)]">
                    {t('rum.applications.originsCount', '{count} 个', {
                      count: (originsEditing ? origins : app.origins)?.length || 0,
                    })}
                  </span>
                </div>
                {originsEditing ? (
                  <>
                    <p className="text-xs text-[var(--color-text-3)]">
                      {t(
                        'rum.detail.originsHint',
                        '精确填写协议、主机和可选端口。其他 Origin 会被拒绝；这仍是滥用控制，Browser Key 不可省略。',
                      )}
                    </p>
                    <OriginEditor origins={origins} onChange={setOrigins} disabled={busy} />
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        type="primary"
                        size="small"
                        disabled={busy}
                        onClick={() => void saveOrigins()}
                      >
                        {t('rum.common.save', '保存')}
                      </Button>
                      <Button
                        size="small"
                        disabled={busy}
                        onClick={() => {
                          setOrigins(app.origins?.slice() || []);
                          setOriginsEditing(false);
                        }}
                      >
                        {t('rum.common.cancel', '取消')}
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-wrap items-center gap-2">
                    <OriginChips origins={app.origins || []} />
                    <RumPermission resource="applications" action="Operate">
                      <Tooltip title={t('rum.common.edit', '编辑')}>
                        <Button
                          type="text"
                          size="small"
                          className="shrink-0 text-[var(--color-text-3)] hover:!text-[var(--color-primary)]"
                          icon={<EditOutlined aria-hidden="true" />}
                          aria-label={t('rum.common.edit', '编辑')}
                          onClick={() => {
                            setOrigins(app.origins?.slice() || []);
                            setOriginsEditing(true);
                          }}
                        />
                      </Tooltip>
                    </RumPermission>
                  </div>
                )}
              </div>
              <div className="mt-4 space-y-2 border-t border-[var(--color-fill-2)] pt-4">
                <span className="text-sm font-medium">{t('rum.budgets.title', '每分钟预算')}</span>
                <p className="text-xs text-[var(--color-text-3)]">
                  {t(
                    'rum.budgets.hint',
                    '超出后网关拒绝这一分钟内的新上报。保存 Origin 不会改动已保存的预算。',
                  )}
                </p>
                {budgetError ? (
                  <p className="text-xs text-[var(--color-error)]">{budgetError}</p>
                ) : null}
                {budgetsEditing ? (
                  <>
                    <BudgetFields
                      value={budgetForm}
                      onChange={(next) => {
                        setBudgetError('');
                        setBudgetForm(next);
                      }}
                      disabled={busy}
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        type="primary"
                        size="small"
                        disabled={busy}
                        onClick={() => void saveBudgets()}
                      >
                        {t('rum.common.save', '保存')}
                      </Button>
                      <Button
                        size="small"
                        disabled={busy}
                        onClick={() => {
                          setBudgetForm(budgetFormFromApi(app.budgets));
                          setBudgetError('');
                          setBudgetsEditing(false);
                        }}
                      >
                        {t('rum.common.cancel', '取消')}
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-[var(--color-text-2)]">
                      {t('rum.budgets.summary', '{requests} 次请求 · {events} 个事件 · {compressed}/{decompressed} MiB', {
                        requests: budgetForm.requestsPerMinute ?? 0,
                        events: budgetForm.eventsPerMinute ?? 0,
                        compressed: budgetForm.compressedMiB ?? 0,
                        decompressed: budgetForm.decompressedMiB ?? 0,
                      })}
                    </span>
                    <RumPermission resource="applications" action="Operate">
                      <Tooltip title={t('rum.common.edit', '编辑')}>
                        <Button
                          type="text"
                          size="small"
                          className="shrink-0 text-[var(--color-text-3)] hover:!text-[var(--color-primary)]"
                          icon={<EditOutlined aria-hidden="true" />}
                          aria-label={t('rum.budgets.edit', '编辑预算')}
                          onClick={() => {
                            setBudgetForm(budgetFormFromApi(app.budgets));
                            setBudgetError('');
                            setBudgetsEditing(true);
                          }}
                        />
                      </Tooltip>
                    </RumPermission>
                  </div>
                )}
              </div>
            </SetupStep>

            <SetupStep n={2} title={t('rum.detail.stepKey', '浏览器密钥')} state={stepKey}>
              <p className="text-xs text-[var(--color-text-3)]">
                {t('rum.detail.keyHint', '该密钥会出现在前端代码中，只能向本应用写入遥测。')}
              </p>
              <KeyPanel
                browserKey={app.browserKeys?.[0] || ''}
                onReissue={() => void reissue()}
                reissuePending={reissuePending}
                autoIssued={freshKey}
              />
            </SetupStep>

            <SetupStep n={3} title={t('rum.detail.stepInstall', '安装与初始化')} state={stepInstall}>
              <p className="text-xs text-[var(--color-text-3)]">
                {t(
                  'rum.detail.installHint',
                  '普通遥测始终全量上报。选择技术栈，将片段放入站点入口后部署并访问一次。',
                )}
              </p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <div className="space-y-1">
                  <label className="text-[11px] font-medium tracking-wide text-[var(--color-text-3)]">
                    {t('rum.detail.environment', '环境')}
                  </label>
                  <Input
                    value={environment}
                    placeholder="production"
                    disabled={!hasKey}
                    onChange={(event) => setEnvironment(event.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] font-medium tracking-wide text-[var(--color-text-3)]">
                    {t('rum.detail.release', '发布版本')}
                  </label>
                  <Input
                    value={release}
                    placeholder={t('rum.detail.releasePlaceholder', '例如 1.0.0')}
                    disabled={!hasKey}
                    onChange={(event) => setRelease(event.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-[11px] font-medium tracking-wide text-[var(--color-text-3)]">
                    {t('rum.detail.replay', '会话回放')}
                  </span>
                  <div className="flex h-8 items-center">
                    <Switch
                      checked={replayEnabled}
                      disabled={!hasKey}
                      onChange={setReplayEnabled}
                      aria-label={t('rum.detail.replay', '会话回放')}
                    />
                  </div>
                </div>
              </div>
              {snippetError ? <p className="text-sm text-[var(--color-fail)]">{snippetError}</p> : null}
              {!hasKey ? (
                <p className="text-xs text-[var(--color-text-3)]">
                  {t('rum.detail.keyEmpty', '尚未签发 Browser Key')}
                </p>
              ) : snippets ? (
                <SnippetTabs
                  codeByTab={{
                    npm: snippets.npm,
                    react: snippets.react,
                    cdn: snippets.cdn,
                    generic: snippets.generic,
                  }}
                  labels={{
                    npm: t('rum.detail.tabNpm', 'NPM（推荐）'),
                    react: t('rum.detail.tabReact', 'React'),
                    cdn: t('rum.detail.tabCdn', 'CDN'),
                    generic: t('rum.detail.tabGeneric', '通用框架'),
                  }}
                />
              ) : (
                <RumCodeSkeleton />
              )}
              <p className="text-xs text-[var(--color-text-3)]">
                {t('rum.detail.deployHint', '部署后访问一次应用，再运行接入自检。')}
              </p>
            </SetupStep>

            <SetupStep n={4} title={t('rum.detail.stepVerify', '验证接入')} state={stepVerify} isLast>
              {projectionPending ? (
                <p className="m-0 text-sm text-[var(--color-warning)]" role="status">
                  {t('rum.detail.projectionPending', '配置正在同步到网关')}
                </p>
              ) : (
                <SelfCheck application={name} />
              )}
            </SetupStep>
          </ol>
        </div>
      ) : null}
    </div>
  );
}
