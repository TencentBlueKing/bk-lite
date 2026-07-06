import React, { useEffect, useMemo, useState } from 'react';
import { Button, Form, Input } from 'antd';

import EntityList from '@/components/entity-list';
import Icon from '@/components/icon';
import OperateModal from '@/components/operate-modal';
import type { ProviderManifest } from '@/app/system-manager/types/integration-center';
import {
  filterIntegrationProvidersByQuery,
  resolveIntegrationProviderIcon,
  getIntegrationCapabilityLabel,
  canEnterCreateInfoStep,
  getCreateModalFooterMode,
  getIntegrationProviderDisplayName
} from '@/app/system-manager/utils/integrationCenter';

interface IntegrationCreateFormValues {
  name: string;
  description?: string;
}

interface CreateIntegrationInstanceModalProps {
  open: boolean;
  providers: ProviderManifest[];
  providersLoading: boolean;
  creating: boolean;
  mode?: 'create' | 'edit';
  initialProvider?: ProviderManifest | null;
  initialValues?: IntegrationCreateFormValues | null;
  t: (key: string, fallback?: string) => string;
  onClose: () => void;
  onSubmit: (payload: {
    provider: ProviderManifest;
    values: IntegrationCreateFormValues;
    continueConfigure: boolean;
  }) => Promise<void>;
}

const CreateIntegrationInstanceModal: React.FC<CreateIntegrationInstanceModalProps> = ({
  open,
  providers,
  providersLoading,
  creating,
  mode = 'create',
  initialProvider = null,
  initialValues = null,
  t,
  onClose,
  onSubmit,
}) => {
  const [form] = Form.useForm<IntegrationCreateFormValues>();
  const [step, setStep] = useState<'provider' | 'basic_info'>('provider');
  const [providerSearch, setProviderSearch] = useState('');
  const [selectedProvider, setSelectedProvider] = useState<ProviderManifest | null>(null);

  useEffect(() => {
    if (!open) {
      setStep('provider');
      setProviderSearch('');
      setSelectedProvider(null);
      form.resetFields();
      return;
    }

    if (mode === 'edit') {
      setStep('basic_info');
      setSelectedProvider(initialProvider);
      form.setFieldsValue({
        name: initialValues?.name || '',
        description: initialValues?.description || '',
      });
      return;
    }

    setStep('provider');
    setProviderSearch('');
    setSelectedProvider(null);
    form.resetFields();
  }, [form, initialProvider, initialValues, mode, open]);

  const filteredProviders = useMemo(
    () => filterIntegrationProvidersByQuery(providers, providerSearch),
    [providerSearch, providers],
  );

  const providerCards = useMemo(
    () => filteredProviders.map((provider) => ({
      id: provider.key,
      name: getIntegrationProviderDisplayName(provider.key, t),
      icon: resolveIntegrationProviderIcon(provider.key),
      description: provider.description || '',
      tagList: provider.capabilities.map((capability) => ({
        name: getIntegrationCapabilityLabel(capability.key, t),
        color: 'processing'
      })),
      raw: provider,
    })),
    [filteredProviders, t],
  );

  const footerMode = getCreateModalFooterMode({
    step,
    hasSelection: canEnterCreateInfoStep(selectedProvider),
    creating,
  });

  const onSelectProvider = (raw: ProviderManifest) => {
    setSelectedProvider(raw);
    setStep('basic_info');
  };

  const handleSubmit = async (continueConfigure: boolean) => {
    if (!selectedProvider) {
      return;
    }

    const values = await form.validateFields();
    await onSubmit({ provider: selectedProvider, values, continueConfigure });
  };

  const editFooter = (
    <div className="flex justify-end gap-2">
      <Button onClick={onClose} disabled={creating}>
        {t('common.cancel')}
      </Button>
      <Button type="primary" onClick={() => handleSubmit(false)} loading={creating}>
        {t('common.save')}
      </Button>
    </div>
  );

  const createFooter = footerMode.showNext ? (
    <Button onClick={onClose} disabled={creating}>
      {t('common.cancel')}
    </Button>
  ) : (
    <>
      <Button onClick={() => setStep('provider')} disabled={creating}>
        {t('common.pre')}
      </Button>
      {footerMode.showCreate ? (
        <Button onClick={() => handleSubmit(false)} loading={creating}>
          {t('system.integrationCenter.createOnly')}
        </Button>
      ) : null}
      {footerMode.showCreateAndConfigure ? (
        <Button type="primary" onClick={() => handleSubmit(true)} loading={creating}>
          {t('system.integrationCenter.createAndConfigure')}
        </Button>
      ) : null}
    </>
  );

  const footer = (<div className="flex justify-end gap-2">{mode === 'edit' ? editFooter : createFooter}</div>);

  return (
    <OperateModal
      title={mode === 'edit' ? t('common.edit') : t('system.integrationCenter.createInstanceTitle')}
      open={open}
      onCancel={onClose}
      width={mode === 'edit' ? 760 : step === 'provider' ? 1080 : 760}
      footer={footer}
      destroyOnClose
    >
      {mode === 'create' && step === 'provider' ? (
        <div className="space-y-4 min-h-[60vh]">
          <Input.Search
            allowClear
            value={providerSearch}
            placeholder={t('system.integrationCenter.searchProviders')}
            onChange={(event) => setProviderSearch(event.target.value)}
            onSearch={setProviderSearch}
          />
          <EntityList
            data={providerCards}
            loading={providersLoading}
            search={false}
            onCardClick={(item: { raw: ProviderManifest }) => onSelectProvider(item.raw)}
          />
        </div>
      ) : (
        <div className="space-y-5">
          {selectedProvider ? (
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)] p-5">
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--color-primary-1)] text-[var(--color-primary)]">
                  <Icon type={resolveIntegrationProviderIcon(selectedProvider.key)} className="text-2xl" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-base font-semibold text-[var(--color-text)]">{getIntegrationProviderDisplayName(selectedProvider.key, t)}</div>
                  <div className="mt-1 text-sm text-[var(--color-text-3)]">
                    {selectedProvider.description || '--'}
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <Form form={form} layout="vertical">
            <Form.Item
              name="name"
              label={t('system.integrationCenter.instanceName')}
              rules={[{ required: true, whitespace: true }]}
            >
              <Input placeholder={t('system.integrationCenter.instanceNamePlaceholder')} />
            </Form.Item>
            <Form.Item
              name="description"
              label={t('system.integrationCenter.usageDescription')}
            >
              <Input.TextArea
                rows={4}
                placeholder={t('system.integrationCenter.usageDescriptionPlaceholder')}
              />
            </Form.Item>
          </Form>
        </div>
      )}
    </OperateModal>
  );
};

export default CreateIntegrationInstanceModal;
