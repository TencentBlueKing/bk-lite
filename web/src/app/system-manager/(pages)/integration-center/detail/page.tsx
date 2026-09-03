// Route: /system-manager/integration-center/detail?id=<instance_id>
'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeftOutlined, CloseCircleFilled, CopyOutlined } from '@ant-design/icons';
import { Alert, App, Badge, Button, Form, Input, InputNumber, Select, Spin, Switch, Tabs, Tooltip } from 'antd';

import { useIntegrationCenterApi } from '@/app/system-manager/api/integration-center';
import type {
  CapabilityExecutionError,
  IntegrationInstance,
  ProviderManifest,
  TemplateField,
  TestConnectionResult,
} from '@/app/system-manager/types/integration-center';
import {
  buildIntegrationFieldRules,
  getAvailableIntegrationTabs,
  getIntegrationBaseCapabilityStatusItems,
  getIntegrationCapabilityLabel,
  getIntegrationDiagnosticMessage,
  getIntegrationDetailSummaryItems,
  getIntegrationDetailTopSectionContent,
  getIntegrationFieldBuckets,
  isIntegrationInstanceStarted,
  resolveIntegrationProviderIcon,
  type IntegrationDetailTab,
} from '@/app/system-manager/utils/integrationCenter';
import { buildLoginAuthCallbackUrl } from '@/app/system-manager/utils/integrationLoginAuthCallbackUrl';
import PermissionWrapper from '@/components/permission';
import TopSection from '@/components/top-section';
import { useTranslation } from '@/utils/i18n';
import { isSilentRequestError } from '@/utils/request';

interface IntegrationDetailFormValues {
  config?: Record<string, unknown>;
}

const saveAndTestMessageKey = 'integration-center-save-and-test';

const IntegrationDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [form] = Form.useForm<IntegrationDetailFormValues>();

  const id = searchParams?.get('id');
  const numericId = id ? Number(id) : NaN;
  const { getInstance, getProviders, testConnection, updateInstance } = useIntegrationCenterApi();

  const [instance, setInstance] = useState<IntegrationInstance | null>(null);
  const [providers, setProviders] = useState<ProviderManifest[]>([]);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isFormDirty, setIsFormDirty] = useState(false);
  const [activeTab, setActiveTab] = useState<IntegrationDetailTab>('base');
  const [lastTestResult, setLastTestResult] = useState<TestConnectionResult | null>(null);
  const [lastTestedTab, setLastTestedTab] = useState<IntegrationDetailTab | null>(null);

  const provider = useMemo(
    () => providers.find((item) => item.key === instance?.provider_key),
    [instance?.provider_key, providers],
  );

  const activeCapability = useMemo(
    () => provider?.capabilities.find((item) => item.key === activeTab),
    [activeTab, provider],
  );

  const activeFields = useMemo(
    () => (activeTab === 'base' ? provider?.instance_template || [] : activeCapability?.connection_template || []),
    [activeCapability?.connection_template, activeTab, provider?.instance_template],
  );

  const baseGroups = useMemo(() => {
    const templates = provider?.instance_templates ? Object.values(provider.instance_templates) : [];
    const groups = templates.flatMap((template) => template.groups);
    return groups.length > 0 ? groups : null;
  }, [provider?.instance_templates]);

  const fieldBuckets = useMemo(
    () => (baseGroups ? { credentialFields: [], publicInterfaceFields: [] } : getIntegrationFieldBuckets(activeFields)),
    [activeFields, baseGroups],
  );

  const availableTabs = useMemo(
    () => (instance ? getAvailableIntegrationTabs(instance) : []),
    [instance],
  );

  const started = useMemo(
    () => (instance ? isIntegrationInstanceStarted(instance.capability_status) : false),
    [instance],
  );

  const summaryItems = useMemo(
    () => (instance ? getIntegrationDetailSummaryItems({ activeTab, instance, t }) : []),
    [activeTab, instance, t],
  );
  const capabilityStatusItems = useMemo(
    () => (instance && activeTab === 'base' ? getIntegrationBaseCapabilityStatusItems({ instance, t }) : []),
    [activeTab, instance, t],
  );

  const topSectionContent = useMemo(
    () => (instance ? getIntegrationDetailTopSectionContent(instance, t) : ''),
    [instance, t],
  );
  const loginAuthCallbackUrl = useMemo(() => {
    if (activeTab !== 'login_auth') {
      return '';
    }
    const result = buildLoginAuthCallbackUrl({
      currentOrigin: typeof window === 'undefined' ? '' : window.location.origin,
      backendCallbackUrl: instance?.login_auth_callback_url || '',
    });
    console.log('[BK-Lite login-auth v2] backend returned:', instance?.login_auth_callback_url, '| rendered:', result);
    return result;
  }, [activeTab, instance?.login_auth_callback_url]);

  const fetchDetailData = async () => {
    if (!id || Number.isNaN(numericId)) {
      setLoading(false);
      router.replace('/system-manager/integration-center');
      return;
    }

    setLoading(true);
    try {
      const [instanceData, providerData] = await Promise.all([
        getInstance(numericId, { redirect_origin: window.location.origin }),
        getProviders(),
      ]);
      setInstance(instanceData);
      setProviders(providerData);
    } catch (error) {
      setInstance(null);
      if (!isSilentRequestError(error)) {
        message.error(t('common.fetchFailed'));
      }
      router.replace('/system-manager/integration-center');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDetailData();
  }, [id]);

  useEffect(() => {
    if (!instance) {
      return;
    }

    const configValues = activeFields.reduce<Record<string, unknown>>((acc, field) => {
      if (!field.write_only) {
        const savedValue = instance.config?.[field.key];
        acc[field.key] = savedValue ?? field.default;
      }
      return acc;
    }, {});

    form.setFieldsValue({ config: configValues });
    setIsFormDirty(false);
  }, [activeFields, form, instance]);

  const saveConfig = async ({ showSuccess = true, refresh = true }: { showSuccess?: boolean; refresh?: boolean } = {}): Promise<boolean> => {
    if (!id || Number.isNaN(numericId) || !instance) {
      return false;
    }

    try {
      const values = await form.validateFields();
      const currentConfig = activeFields.reduce<Record<string, unknown>>((acc, field) => {
        const fieldValue = values.config?.[field.key];
        if (fieldValue !== undefined) {
          acc[field.key] = fieldValue;
        }
        return acc;
      }, {});

      setSaving(true);
      await updateInstance(numericId, {
        name: instance.name,
        provider_key: instance.provider_key,
        description: instance.description || '',
        config: currentConfig,
        config_scope: activeTab,
      });
      if (showSuccess) {
        message.success(t('common.saveSuccess'));
      }
      setIsFormDirty(false);
      if (activeTab === 'base' || lastTestedTab === activeTab) {
        setLastTestResult(null);
        setLastTestedTab(null);
      }
      if (refresh) {
        await fetchDetailData();
      }
      return true;
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) {
        return false;
      }
      if (!isSilentRequestError(error)) {
        message.error(t('common.saveFailed'));
      }
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    await saveConfig();
  };

  const handleToggleCapability = async (enabled: boolean) => {
    if (!id || Number.isNaN(numericId) || !instance || activeTab === 'base') {
      return;
    }

    setSaving(true);
    try {
      await updateInstance(numericId, {
        name: instance.name,
        provider_key: instance.provider_key,
        description: instance.description || '',
        capability_enabled: {
          ...instance.capability_enabled,
          [activeTab]: enabled,
        },
      });
      message.success(
        enabled ? t('system.integrationCenter.capabilityEnabled') : t('system.integrationCenter.capabilityDisabled'),
      );
      fetchDetailData();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const runTestRequest = async ({ savedBeforeTest = false, isPipeline = false } = {}) => {
    if (!id || Number.isNaN(numericId)) {
      return;
    }

    if (!isPipeline) {
      setTesting(true);
    }
    try {
      const result = await testConnection(numericId, activeTab === 'base' ? undefined : activeTab);
      const testSucceeded = result.data.success;
      const successMessage = activeTab === 'im_group'
        ? t('system.integrationCenter.checkGroupCapabilitySuccess')
        : savedBeforeTest
          ? t('system.integrationCenter.saveAndTestSuccess')
          : t('system.integrationCenter.testSuccess');
      const unavailable = result.data.errors?.[0]?.code === 'provider.unavailable';
      const failedMessage = unavailable
        ? t('system.integrationCenter.providerUnavailable')
        : activeTab === 'im_group'
          ? t('system.integrationCenter.checkGroupCapabilityFailed')
          : t('system.integrationCenter.testFailed');
      setLastTestResult({ ...result, result: testSucceeded });
      setLastTestedTab(activeTab);
      message[testSucceeded ? 'success' : 'error'](
        isPipeline
          ? {
            key: saveAndTestMessageKey,
            content: testSucceeded ? successMessage : failedMessage,
          }
          : testSucceeded
            ? successMessage
            : failedMessage,
      );
      await fetchDetailData();
    } catch (error) {
      if (!isSilentRequestError(error)) {
        message.error(
          isPipeline
            ? { key: saveAndTestMessageKey, content: t('system.integrationCenter.testFailed') }
            : t('system.integrationCenter.testFailed'),
        );
      }
    } finally {
      setTesting(false);
    }
  };

  const handleTestConnection = async () => {
    if (isFormDirty) {
      modal.confirm({
        title: t('system.integrationCenter.saveAndTestTitle'),
        content: t('system.integrationCenter.saveAndTestContent'),
        okText: t('system.integrationCenter.saveAndTest'),
        cancelText: t('common.cancel'),
        onOk: async () => {
          setTesting(true);
          message.loading({
            key: saveAndTestMessageKey,
            content: t('system.integrationCenter.savingAndTesting'),
            duration: 0,
          });
          const saved = await saveConfig({ showSuccess: false, refresh: false });
          if (saved) {
            await runTestRequest({ savedBeforeTest: true, isPipeline: true });
          } else {
            message.destroy(saveAndTestMessageKey);
            setTesting(false);
          }
        },
      });
      return;
    }

    await runTestRequest();
  };

  const handleCopyLoginAuthCallbackUrl = async () => {
    if (!loginAuthCallbackUrl) {
      return;
    }

    try {
      await navigator.clipboard.writeText(loginAuthCallbackUrl);
      message.success(t('common.copySuccess'));
    } catch {
      message.error(t('common.copyFailed'));
    }
  };

  const renderTemplateField = (field: TemplateField) => {
    const fieldName = ['config', field.key] as (string | number)[];
    const baseRules = buildIntegrationFieldRules(field);
    const placeholder = field.write_only
      ? t('system.integrationCenter.keepSecretPlaceholder')
      : field.placeholder || undefined;

    switch (field.field_type) {
      case 'textarea':
        return (
          <Form.Item key={field.key} name={fieldName} label={field.label} rules={baseRules} tooltip={field.help_text || undefined}>
            <Input.TextArea rows={4} placeholder={placeholder} />
          </Form.Item>
        );
      case 'password':
        return (
          <Form.Item key={field.key} name={fieldName} label={field.label} rules={baseRules} tooltip={field.help_text || undefined}>
            <Input.Password placeholder={placeholder} />
          </Form.Item>
        );
      case 'number':
        return (
          <Form.Item key={field.key} name={fieldName} label={field.label} rules={baseRules} tooltip={field.help_text || undefined}>
            <InputNumber className="w-full" placeholder={placeholder} />
          </Form.Item>
        );
      case 'boolean':
        return (
          <Form.Item key={field.key} name={fieldName} label={field.label} tooltip={field.help_text || undefined} valuePropName="checked">
            <Switch />
          </Form.Item>
        );
      case 'select':
        return (
          <Form.Item key={field.key} name={fieldName} label={field.label} rules={baseRules} tooltip={field.help_text || undefined}>
            <Select
              options={field.options.map((item) => ({
                value: item.value as string | number | boolean,
                label: String(item.label),
              }))}
              placeholder={placeholder}
            />
          </Form.Item>
        );
      default:
        return (
          <Form.Item key={field.key} name={fieldName} label={field.label} rules={baseRules} tooltip={field.help_text || undefined}>
            <Input placeholder={placeholder} />
          </Form.Item>
        );
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[300px] items-center justify-center">
        <Spin spinning />
      </div>
    );
  }

  if (!instance) {
    return null;
  }

  const testDisabled = activeTab !== 'base' && instance.status !== 'ready';
  const diagnostic: CapabilityExecutionError | null = lastTestResult?.data.errors?.[0] || null;
  const showErrorSummary = Boolean(lastTestResult && !lastTestResult.result && lastTestedTab === activeTab);
  const diagnosticFieldLabel = diagnostic?.field
    ? activeFields.find((field) => field.key === diagnostic.field)?.label || diagnostic.field
    : '';
  const diagnosticDetail =
    diagnostic?.code === 'provider.unavailable'
      ? t('system.integrationCenter.providerUnavailable')
      : diagnostic?.detail || diagnostic?.message || '';

  return (
    <div className="w-full space-y-4">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <TopSection
            title={instance.name}
            content={topSectionContent}
            iconType={resolveIntegrationProviderIcon(instance.provider_key)}
          />
        </div>
      </div>

      <section className="grid overflow-hidden rounded-md bg-[var(--color-bg)] shadow-sm xl:grid-cols-[minmax(0,8.4fr)_minmax(200px,1.6fr)]">
        <div className="px-5 py-4">
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as IntegrationDetailTab)}
            items={availableTabs.map((tabKey) => ({
              key: tabKey,
              label: tabKey === 'base' ? t('system.integrationCenter.baseConnection') : getIntegrationCapabilityLabel(tabKey, t),
            }))}
          />

          {activeTab === 'base' ? (
            <div className="mt-1">
              <Form form={form} layout="vertical" onValuesChange={() => setIsFormDirty(true)}>
                {instance.provider_key === 'wechat' ? (
                  <Alert
                    className="mb-4"
                    type="info"
                    showIcon
                    message={t('system.integrationCenter.wechatBaseValidationNotice')}
                  />
                ) : null}
                {baseGroups ? (
                  baseGroups.map((group, idx) => (
                    <div
                      key={group.key}
                      className={idx < baseGroups.length - 1 ? 'border-b border-[var(--color-border)] py-4' : 'pt-4'}
                    >
                      <div className="mb-4 text-[16px] font-semibold text-[var(--color-text)]">{group.title}</div>
                      {group.description ? (
                        <div className="mb-4 text-[14px] text-[var(--color-text-3)]">{group.description}</div>
                      ) : null}
                      {group.fields.map((field) => renderTemplateField(field))}
                    </div>
                  ))
                ) : (
                  <>
                    {fieldBuckets.credentialFields.length > 0 ? (
                      <div className="border-b border-[var(--color-border)] py-4">
                        <div className="mb-4 text-[16px] font-semibold text-[var(--color-text)]">
                          {t('system.integrationCenter.applicationCredential')}
                        </div>
                        {fieldBuckets.credentialFields.map((field) => renderTemplateField(field))}
                      </div>
                    ) : null}

                    {fieldBuckets.publicInterfaceFields.length > 0 ? (
                      <div className={fieldBuckets.credentialFields.length > 0 ? 'py-4' : 'pt-4'}>
                        <div className="mb-4 text-[16px] font-semibold text-[var(--color-text)]">
                          {t('system.integrationCenter.requestConfig')}
                        </div>
                        {fieldBuckets.publicInterfaceFields.map((field) => renderTemplateField(field))}
                      </div>
                    ) : null}
                  </>
                )}
              </Form>
            </div>
          ) : activeTab === 'im_group' ? (
            <div className="space-y-4 py-4">
              <Alert
                type="info"
                showIcon
                message={t('system.integrationCenter.imGroupOverviewTitle')}
                description={(
                  <div className="space-y-1">
                    <div>{t('system.integrationCenter.imGroupOverviewDescription')}</div>
                    <div>{t('system.integrationCenter.imGroupNoExtraConfig')}</div>
                  </div>
                )}
              />
              <div className="rounded-md border border-[var(--color-border)] px-5 py-4">
                <div className="mb-3 text-[16px] font-semibold text-[var(--color-text)]">
                  {t('system.integrationCenter.imGroupPreparationTitle')}
                </div>
                <ul className="list-disc space-y-2 pl-5 text-[14px] leading-6 text-[var(--color-text-2)]">
                  <li>{t('system.integrationCenter.imGroupCredentialRequirement')}</li>
                  <li>{t('system.integrationCenter.imGroupUserMappingRequirement')}</li>
                  <li>
                    {instance.provider_key === 'wecom'
                      ? t('system.integrationCenter.imGroupWeComPermissionHint')
                      : t('system.integrationCenter.imGroupFeishuPermissionHint')}
                  </li>
                </ul>
              </div>
            </div>
          ) : (
            <div className="pt-1">
              <Form form={form} layout="vertical" onValuesChange={() => setIsFormDirty(true)}>
                <div className="py-4">
                  <div className="mb-4 text-[16px] font-semibold text-[var(--color-text)]">
                    {t('system.integrationCenter.interfaceConfig')}
                  </div>
                  {activeFields.length > 0 ? (
                    <>
                      {activeFields.map((field) => renderTemplateField(field))}
                      {activeTab === 'login_auth' ? (
                        <Form.Item
                          label={t('system.integrationCenter.loginAuthCallbackUrl')}
                          className="mb-0"
                        >
                          <Input
                            value={loginAuthCallbackUrl}
                            readOnly
                            suffix={
                              <Tooltip title={t('common.copy')}>
                                <button
                                  type="button"
                                  aria-label={t('common.copy')}
                                  className="inline-flex items-center justify-center text-[var(--color-primary)] hover:text-[#1F5DE0]"
                                  onClick={handleCopyLoginAuthCallbackUrl}
                                >
                                  <CopyOutlined />
                                </button>
                              </Tooltip>
                            }
                          />
                          <div className="mt-2 text-[12px] text-[var(--color-text-3)]">
                            {t('system.integrationCenter.loginAuthCallbackUrlHint')}
                          </div>
                        </Form.Item>
                      ) : null}
                    </>
                  ) : (
                    <div className="rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-6 text-[14px] text-[var(--color-text-3)]">
                      {t('system.integrationCenter.noInterfaceConfig')}
                    </div>
                  )}
                </div>
              </Form>
            </div>
          )}

          <div className="flex flex-col gap-3 border-t border-[var(--color-border)] pt-2">
            <div className="text-[13px] text-[var(--color-text-3)]">
              {activeTab === 'base'
                ? t('system.integrationCenter.baseConnectionHint')
                : activeTab === 'im_group'
                  ? t('system.integrationCenter.imGroupCheckHint')
                  : started
                    ? t('system.integrationCenter.startedHint')
                    : t('system.integrationCenter.notStartedHint')}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 mt-3">
              <Button
                type="link"
                icon={<ArrowLeftOutlined />}
                className="px-0"
                onClick={() => router.push('/system-manager/integration-center')}
              >
                {t('system.integrationCenter.back')}
              </Button>
              <div className="flex flex-wrap items-center gap-3">
                {activeTab !== 'im_group' ? (
                  <PermissionWrapper requiredPermissions={['Edit']}>
                    <Button onClick={handleSave} loading={saving}>
                      {t('common.save')}
                    </Button>
                  </PermissionWrapper>
                ) : null}
                <PermissionWrapper requiredPermissions={['Edit']}>
                  <Tooltip title={testDisabled ? t('system.integrationCenter.baseConnectionRequired') : undefined}>
                    <span>
                      <Button onClick={handleTestConnection} loading={testing} disabled={testDisabled} type="primary">
                        {activeTab === 'im_group'
                          ? t('system.integrationCenter.checkGroupCapability')
                          : t('system.integrationCenter.testRequest')}
                      </Button>
                    </span>
                  </Tooltip>
                </PermissionWrapper>
                {activeTab !== 'base' && (
                  <PermissionWrapper requiredPermissions={['Edit']}>
                    <Button
                      onClick={() => handleToggleCapability(!instance.capability_enabled?.[activeTab])}
                      loading={saving}
                    >
                      {instance.capability_enabled?.[activeTab]
                        ? t('system.integrationCenter.disableCapability')
                        : t('system.integrationCenter.enableCapability')}
                    </Button>
                  </PermissionWrapper>
                )}
              </div>
            </div>
          </div>
        </div>

        <aside className="border-l border-[var(--color-border)] px-5 py-5">
          <div className="mb-4 text-base font-semibold text-[var(--color-text)]">{t('system.integrationCenter.statusSummary')}</div>
          <div className="space-y-3">
            {summaryItems.map((item) => (
              <div
                key={item.label}
                className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2"
              >
                <div className="mb-1 text-xs text-[var(--color-text-3)]">{item.label}</div>
                <Badge
                  status={item.tone === 'success' ? 'success' : item.tone === 'error' ? 'error' : 'default'}
                  text={<span className="text-[14px] text-[var(--color-text)]">{item.value}</span>}
                />
              </div>
            ))}
          </div>
          {capabilityStatusItems.length > 0 ? (
            <div className="mt-5 border-t border-[var(--color-border)] pt-4">
              <div className="mb-2 text-sm font-medium text-[var(--color-text)]">
                {t('system.integrationCenter.capabilityStatus')}
              </div>
              <div className="space-y-3">
                {capabilityStatusItems.map((item) => (
                  <div
                    key={item.label}
                    className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2"
                  >
                    <Tooltip title={item.label}>
                      <div className="mb-1 truncate text-xs text-[var(--color-text-3)]">{item.label}</div>
                    </Tooltip>
                    <Badge
                      status={item.tone === 'success' ? 'success' : item.tone === 'error' ? 'error' : 'default'}
                      text={<span className="whitespace-nowrap text-[14px] text-[var(--color-text)]">{item.value}</span>}
                    />
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {showErrorSummary ? (
            <div
              className="mt-4 rounded-md border px-3 py-3"
              style={{
                borderColor: 'var(--color-fail)',
                backgroundColor: 'color-mix(in srgb, var(--color-fail) 6%, var(--color-bg))',
              }}
            >
              <div className="flex items-center gap-2 text-[14px] font-medium text-[var(--color-text)]">
                <CloseCircleFilled className="text-[var(--color-fail)]" />
                <span>{t('system.integrationCenter.errorSummary')}</span>
              </div>
              <div className="mt-2 space-y-1 text-[13px] leading-5 text-[var(--color-text-2)]">
                <div>{getIntegrationDiagnosticMessage(diagnostic?.code, t)}</div>
                {diagnosticFieldLabel ? (
                  <div className="break-words">{`${t('system.integrationCenter.problemField')}: ${diagnosticFieldLabel}`}</div>
                ) : null}
                {diagnostic?.external_code ? (
                  <div className="break-words">{`${t('system.integrationCenter.externalErrorCode')}: ${diagnostic.external_code}`}</div>
                ) : null}
                {diagnosticDetail ? (
                  <div className="break-words">{`${t('system.integrationCenter.errorDetail')}: ${diagnosticDetail}`}</div>
                ) : null}
              </div>
            </div>
          ) : null}
        </aside>
      </section>
    </div>
  );
};

export default IntegrationDetailPage;
