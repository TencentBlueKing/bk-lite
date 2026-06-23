// Route: /system-manager/integration-center/detail?id=<instance_id>
'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button, Form, Input, InputNumber, Modal, Select, Spin, Switch, Tabs, message } from 'antd';

import PermissionWrapper from '@/components/permission';
import TopSection from '@/components/top-section';
import { useTranslation } from '@/utils/i18n';
import { useIntegrationCenterApi } from '@/app/system-manager/api/integration-center';
import type { IntegrationInstance, ProviderManifest, TemplateField } from '@/app/system-manager/types/integration-center';
import { isSilentRequestError } from '@/utils/request';

import {
  getIntegrationCapabilityLabel,
  getIntegrationCapabilityStatusText,
  getIntegrationTestStatusText,
  isIntegrationInstanceStarted,
  resolveIntegrationProviderIcon,
  getAvailableIntegrationTabs,
  type IntegrationDetailTab
} from '@/app/system-manager/utils/intergrationCenter';

interface IntegrationDetailFormValues {
  config?: Record<string, unknown>;
}

const IntegrationDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [form] = Form.useForm<IntegrationDetailFormValues>();

  const id = searchParams?.get('id');
  const { getInstance, getProviders, testConnection, updateInstance } = useIntegrationCenterApi();

  const [instance, setInstance] = useState<IntegrationInstance | null>(null);
  const [providers, setProviders] = useState<ProviderManifest[]>([]);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isFormDirty, setIsFormDirty] = useState(false);
  const [activeTab, setActiveTab] = useState<IntegrationDetailTab>('base');
  const numericId = id ? Number(id) : NaN;

  const fetchDetailData = async () => {
    if (!id || Number.isNaN(numericId)) {
      setLoading(false);
      router.replace('/system-manager/integration-center');
      return;
    }

    setLoading(true);
    try {
      const [instanceData, providerData] = await Promise.all([
        getInstance(numericId),
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
    const groups = templates.flatMap((tpl) => tpl.groups);
    return groups.length > 0 ? groups : null;
  }, [provider?.instance_templates]);

  const credentialFields = useMemo(
    () => (baseGroups ? [] : activeFields.filter((field) => field.key === 'app_id' || field.key === 'app_secret')),
    [activeFields, baseGroups],
  );

  const publicInterfaceFields = useMemo(
    () => (baseGroups ? [] : activeFields.filter((field) => field.key !== 'app_id' && field.key !== 'app_secret')),
    [activeFields, baseGroups],
  );

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
    console.log(instance);
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

    const nextCapabilityEnabled = {
      ...instance.capability_enabled,
      [activeTab]: enabled,
    };

    setSaving(true);
    try {
      await updateInstance(numericId, {
        name: instance.name,
        provider_key: instance.provider_key,
        description: instance.description || '',
        capability_enabled: nextCapabilityEnabled,
      });
      message.success(enabled ? t('system.integrationCenter.capabilityEnabled') : t('system.integrationCenter.capabilityDisabled'));
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
        title: t('system.integrationCenter.unsavedConfigTitle', '配置未保存'),
        content: t('system.integrationCenter.unsavedConfigContent', '当前配置有未保存的修改，请先保存后再测试。'),
        okText: t('common.save', '保存'),
        cancelText: t('common.cancel', '取消'),
        onOk: handleSave,
      });
      return;
    }

    setTesting(true);
    try {
      const result = await testConnection(numericId, activeTab === 'base' ? undefined : activeTab);
      if (result.result) {
        message.success(t('system.integrationCenter.testSuccess'));
      } else {
        message.error(t('system.integrationCenter.testFailed'));
      }
      fetchDetailData();
    } catch (error) {
      if (!isSilentRequestError(error)) {
        message.error(t('system.integrationCenter.testFailed'));
      }
    } finally {
      setTesting(false);
    }
  };

  const renderTemplateField = (field: TemplateField) => {
    const fieldName = ['config', field.key] as (string | number)[];
    const baseRules = field.required
      ? [{ required: !field.write_only, whitespace: field.field_type === 'string' || field.field_type === 'textarea' }]
      : undefined;
    const placeholder = field.write_only
      ? t('system.integrationCenter.keepSecretPlaceholder', '如无需变更可留空')
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

  const started = isIntegrationInstanceStarted(instance.capability_status);
  const availableTabs = getAvailableIntegrationTabs(instance);
  const currentCapabilityStatus = activeTab === 'base' ? instance.status : instance.capability_status?.[activeTab];
  const providerLabel = `${t('system.integrationCenter.providerTypeLabel', t('system.integrationCenter.provider', '集成类型'))}：${instance.provider?.name ?? instance.provider_key}`;
  const topSectionContent = instance.description ? `${providerLabel}，${instance.description}` : providerLabel;

  return (
    <div className="w-full space-y-4">
      <div className="flex items-center gap-3">
        <Button icon={<ArrowLeftOutlined />} type='text' onClick={() => router.push('/system-manager/integration-center')} />
        <div className="min-w-0 flex-1">
          <TopSection
            title={instance.name}
            content={topSectionContent}
            iconType={resolveIntegrationProviderIcon(instance.provider_key)}
          />
        </div>
      </div>

      <section className="overflow-hidden rounded-[22px] bg-white shadow-sm">
        <div className="px-6 pt-4">
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as IntegrationDetailTab)}
            items={availableTabs.map((tabKey) => ({
              key: tabKey,
              label: tabKey === 'base' ? t('system.integrationCenter.baseConnection', '基础连接') : getIntegrationCapabilityLabel(tabKey, t),
            }))}
          />
        </div>

        {activeTab === 'base' ? (
          <div className="px-6 py-6">
            <Form form={form} layout="vertical" onValuesChange={() => setIsFormDirty(true)}>
              {baseGroups ? (
                baseGroups.map((group, idx) => (
                  <div
                    key={group.key}
                    className={idx < baseGroups.length - 1 ? 'mb-5 border-b border-[var(--color-border)] pb-5' : ''}
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
                  {credentialFields.length > 0 ? (
                    <div className="border-b border-[var(--color-border)] pb-5">
                      <div className="mb-4 text-[16px] font-semibold text-[var(--color-text)]">
                        {t('system.integrationCenter.applicationCredential', '应用凭证')}
                      </div>
                      {credentialFields.map((field) => renderTemplateField(field))}
                    </div>
                  ) : null}

                  {publicInterfaceFields.length > 0 ? (
                    <div className={credentialFields.length > 0 ? 'pt-5' : ''}>
                      <div className="mb-4 text-[16px] font-semibold text-[var(--color-text)]">
                        {t('system.integrationCenter.requestConfig', '公共接口')}
                      </div>
                      {publicInterfaceFields.map((field) => renderTemplateField(field))}
                    </div>
                  ) : null}
                </>
              )}
            </Form>
          </div>
        ) : (
          <div className="px-6 py-6">
            <Form form={form} layout="vertical" onValuesChange={() => setIsFormDirty(true)}>
              <div className="mb-4 text-[16px] font-semibold text-[var(--color-text)]">
                {t('system.integrationCenter.interfaceConfig', '接口配置')}
              </div>
              {activeFields.length > 0 ? (
                activeFields.map((field) => renderTemplateField(field))
              ) : (
                <div className="rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-6 text-[14px] text-[var(--color-text-3)]">
                  {t('system.integrationCenter.noInterfaceConfig', '当前能力暂无额外接口配置。')}
                </div>
              )}
            </Form>
          </div>
        )}

        <div className="flex flex-col gap-3 border-t border-[var(--color-border)] px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="text-[13px] text-[var(--color-text-3)]">
            {activeTab === 'base'
              ? t('system.integrationCenter.baseConnectionHint', '完成基础连接保存与测试后，才能继续配置各能力。')
              : started
                ? t('system.integrationCenter.startedHint', '当前实例至少已有一个能力完成启动。')
                : t('system.integrationCenter.notStartedHint', '当前实例尚未启动，完成基础连接保存与测试后会更新卡片状态。')}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="text-[14px] text-[var(--color-text-2)]">
              {t('system.integrationCenter.testStatus', '测试状态')}：
              <span className="ml-2 inline-flex items-center gap-2">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${
                    currentCapabilityStatus === 'ready'
                      ? 'bg-emerald-500'
                      : currentCapabilityStatus === 'verification_failed'
                        ? 'bg-red-500'
                        : 'bg-slate-400'
                  }`}
                />
                <span className="text-[var(--color-text)]">
                  {activeTab === 'base'
                    ? getIntegrationTestStatusText(instance.status, t)
                    : getIntegrationCapabilityStatusText(currentCapabilityStatus || 'pending_verification', t)}
                </span>
              </span>
            </div>

            {activeTab !== 'base' && (
              <div className="text-[14px] text-[var(--color-text-2)]">
                {t('system.integrationCenter.platformStatus', '平台状态')}：
                <span className="ml-2 inline-flex items-center gap-2">
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${
                      instance.capability_enabled?.[activeTab] ? 'bg-emerald-500' : 'bg-slate-400'
                    }`}
                  />
                  <span className="text-[var(--color-text)]">
                    {instance.capability_enabled?.[activeTab]
                      ? t('system.integrationCenter.enabled', '已启用')
                      : t('system.integrationCenter.disabled', '未启用')}
                  </span>
                </span>
              </div>
            )}

            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button onClick={handleSave} loading={saving}>
                {t('common.save', '保存')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button onClick={handleTestConnection} loading={testing}>
                {testing
                  ? t('system.integrationCenter.testing', '测试中')
                  : activeTab === 'base'
                    ? t('system.integrationCenter.testAllConnections', '测试全部连接')
                    : t('system.integrationCenter.testConnection', '测试连接')}
              </Button>
            </PermissionWrapper>
            {activeTab !== 'base' && (
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button
                  onClick={() => handleToggleCapability(!instance.capability_enabled?.[activeTab])}
                  loading={saving}
                >
                  {instance.capability_enabled?.[activeTab]
                    ? t('system.integrationCenter.disableCapability', '禁用能力')
                    : t('system.integrationCenter.enableCapability', '启用能力')}
                </Button>
              </PermissionWrapper>
            )}
          </div>
        </div>
      </section>
    </div>
  );
};

export default IntegrationDetailPage;
