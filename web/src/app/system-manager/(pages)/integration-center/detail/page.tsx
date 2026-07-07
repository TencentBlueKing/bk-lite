// Route: /system-manager/integration-center/detail?id=<instance_id>
'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeftOutlined, CopyOutlined } from '@ant-design/icons';
import { Badge, Button, Form, Input, InputNumber, Modal, Select, Spin, Switch, Tabs, Tooltip, message } from 'antd';

import { useIntegrationCenterApi } from '@/app/system-manager/api/integration-center';
import type { IntegrationInstance, ProviderManifest, TemplateField } from '@/app/system-manager/types/integration-center';
import {
  buildIntegrationFieldRules,
  getAvailableIntegrationTabs,
  getIntegrationCapabilityLabel,
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

const IntegrationDetailPage: React.FC = () => {
  const { t } = useTranslation();
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

  const topSectionContent = useMemo(
    () => (instance ? getIntegrationDetailTopSectionContent(instance, t) : ''),
    [instance, t],
  );
  const loginAuthCallbackUrl = useMemo(() => {
    if (activeTab !== 'login_auth') {
      return '';
    }
    return buildLoginAuthCallbackUrl({
      currentOrigin: typeof window === 'undefined' ? '' : window.location.origin,
      backendCallbackUrl: instance?.login_auth_callback_url || '',
    });
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

  const handleSave = async () => {
    if (!id || Number.isNaN(numericId) || !instance) {
      return;
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
      message.success(t('common.saveSuccess'));
      fetchDetailData();
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) {
        return;
      }
      if (!isSilentRequestError(error)) {
        message.error(t('common.saveFailed'));
      }
    } finally {
      setSaving(false);
    }
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

  const handleTestConnection = async () => {
    if (!id || Number.isNaN(numericId)) {
      return;
    }

    if (isFormDirty) {
      Modal.confirm({
        title: t('system.integrationCenter.unsavedConfigTitle'),
        content: t('system.integrationCenter.unsavedConfigContent'),
        okText: t('common.save'),
        cancelText: t('common.cancel'),
        onOk: handleSave,
      });
      return;
    }

    setTesting(true);
    try {
      const result = await testConnection(numericId, activeTab === 'base' ? undefined : activeTab);
      message[result.result ? 'success' : 'error'](
        result.result ? t('system.integrationCenter.testSuccess') : t('system.integrationCenter.testFailed'),
      );
      fetchDetailData();
    } catch (error) {
      if (!isSilentRequestError(error)) {
        message.error(t('system.integrationCenter.testFailed'));
      }
    } finally {
      setTesting(false);
    }
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

      <section className="grid overflow-hidden rounded-md bg-white shadow-sm xl:grid-cols-[minmax(0,8.4fr)_minmax(200px,1.6fr)]">
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
                <PermissionWrapper requiredPermissions={['Edit']}>
                  <Button onClick={handleSave} loading={saving}>
                    {t('common.save')}
                  </Button>
                </PermissionWrapper>
                <PermissionWrapper requiredPermissions={['Edit']}>
                  <Button onClick={handleTestConnection} loading={testing} type="primary">
                    {testing
                      ? t('system.integrationCenter.testing')
                      : activeTab === 'base'
                        ? t('system.integrationCenter.testAllConnections')
                        : t('system.integrationCenter.testConnection')}
                  </Button>
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
        </aside>
      </section>
    </div>
  );
};

export default IntegrationDetailPage;
