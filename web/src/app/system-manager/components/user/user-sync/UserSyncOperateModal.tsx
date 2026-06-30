import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Form,
  Input,
  Select,
} from 'antd';

import OperateModal from '@/components/operate-modal';
import type { ProviderManifest } from '@/app/system-manager/types/integration-center';
import type {
  AvailableInstance,
  UserSyncSourceCreateFormValues,
} from '@/app/system-manager/types/user-sync';
import {
  getDefaultDepartmentIdType,
  mergeUserSyncBusinessConfigWithDefaults,
  getWriteOnlyKeys,
  isDepartmentSelectMode,
  resolveUserSyncTemplate,
} from '@/app/system-manager/utils/userSyncUtils';
import { formatIntegrationInstanceDisplayName } from '@/app/system-manager/utils/intergrationCenter';
import { type MappingRow, toMappingRows } from '@/app/system-manager/utils/userSyncPageUtils';
import UserSyncConfigFields from '@/app/system-manager/components/user/user-sync/UserSyncConfigFields';

interface UserSyncOperateModalProps {
  open: boolean;
  loading: boolean;
  previewLoading: boolean;
  availableInstances: AvailableInstance[];
  providers: ProviderManifest[];
  providersLoading: boolean;
  t: (key: string, fallback?: string) => string;
  onClose: () => void;
  onPreview: (values: UserSyncSourceCreateFormValues, mappingRows: MappingRow[], writeOnlyKeys: Set<string>) => void;
  onSubmit: (values: UserSyncSourceCreateFormValues, mappingRows: MappingRow[]) => void;
}

const UserSyncOperateModal: React.FC<UserSyncOperateModalProps> = ({
  open,
  loading,
  previewLoading,
  availableInstances,
  providers,
  providersLoading,
  t,
  onClose,
  onPreview,
  onSubmit,
}) => {
  const [form] = Form.useForm<UserSyncSourceCreateFormValues>();
  const [currentStep, setCurrentStep] = useState(1);
  const [mappingRows, setMappingRows] = useState<MappingRow[]>(toMappingRows({}));
  const watchedInstanceId = Form.useWatch('integration_instance', form);
  const selectedInstanceId = watchedInstanceId ?? form.getFieldValue('integration_instance');
  const previousInstanceIdRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!open) {
      setCurrentStep(1);
      setMappingRows(toMappingRows({}));
      form.resetFields();
      return;
    }
    form.setFieldsValue({
      description: '',
      business_config: {},
    });
  }, [open, form]);

  const resolvedTemplate = useMemo(
    () => resolveUserSyncTemplate(selectedInstanceId, availableInstances, providers),
    [selectedInstanceId, availableInstances, providers],
  );

  const writeOnlyKeys = useMemo(() => getWriteOnlyKeys(resolvedTemplate), [resolvedTemplate]);

  useEffect(() => {
    if (!open || !selectedInstanceId) return;
    if (previousInstanceIdRef.current === selectedInstanceId) return;
    previousInstanceIdRef.current = selectedInstanceId;

    const nextBusinessConfig = mergeUserSyncBusinessConfigWithDefaults(
      form.getFieldValue('business_config') || {},
      resolvedTemplate,
      { excludeRootScope: true },
    );

    if (isDepartmentSelectMode(resolvedTemplate)) {
      nextBusinessConfig.root_department_id = '__all__';
      const defaultDepartmentIdType = getDefaultDepartmentIdType(resolvedTemplate);
      if (defaultDepartmentIdType) {
        nextBusinessConfig.department_id_type = defaultDepartmentIdType;
      }
    } else {
      delete nextBusinessConfig.root_department_id;
      delete nextBusinessConfig.department_id_type;
    }

    form.setFieldValue('business_config', nextBusinessConfig);
  }, [form, open, resolvedTemplate, selectedInstanceId]);

  useEffect(() => {
    if (open || selectedInstanceId) return;
    previousInstanceIdRef.current = undefined;
  }, [open, selectedInstanceId]);

  const handleNextStep = async () => {
    try {
      await form.validateFields(['name', 'integration_instance', 'root_group_name', 'description']);
      setCurrentStep(2);
    } catch {
      // keep current step
    }
  };

  const handleSubmit = async () => {
    try {
      await form.validateFields();
    } catch {
      return;
    }
    onSubmit(form.getFieldsValue(true) as UserSyncSourceCreateFormValues, mappingRows);
  };

  const handlePreview = async () => {
    try {
      await form.validateFields();
    } catch {
      return;
    }
    onPreview(form.getFieldsValue(true) as UserSyncSourceCreateFormValues, mappingRows, writeOnlyKeys);
  };

  const footer = currentStep === 1 ? (
    <div className="flex justify-end gap-2">
      <Button type="primary" onClick={handleNextStep} loading={loading}>
        {t('common.next')}
      </Button>
    </div>
  ) : (
    <div className="flex justify-end gap-2">
      <Button onClick={() => setCurrentStep(1)} disabled={loading || previewLoading}>
        {t('common.pre')}
      </Button>
      <Button onClick={handlePreview} loading={previewLoading} disabled={loading}>
        {t('system.integrationCenter.testConnection')}
      </Button>
      <Button type="primary" onClick={handleSubmit} loading={loading} disabled={previewLoading}>
        {t('system.user.userSyncPage.addSource')}
      </Button>
    </div>
  );

  const instanceOptions = useMemo(
    () =>
      availableInstances.map((inst) => ({
        value: inst.id,
        label: formatIntegrationInstanceDisplayName(inst, t),
      })),
    [availableInstances, t],
  );

  return (
    <OperateModal
      title={t('system.user.userSyncPage.addSource')}
      open={open}
      onCancel={onClose}
      width={800}
      footer={footer}
      destroyOnClose
    >
      <div className="mb-5 text-[14px] text-[var(--color-text-3)]">
        {t('system.user.userSyncPage.modalDesc')}
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <button
          type="button"
          className={`rounded-2xl border px-4 py-3 text-left transition ${currentStep === 1 ? 'border-[var(--color-primary)] bg-emerald-50' : 'border-[var(--color-border)] bg-white'
            }`}
          onClick={() => setCurrentStep(1)}
        >
          <div className="flex items-center gap-3">
            <div
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[13px] ${currentStep === 1 ? 'bg-[var(--color-primary)] text-white' : 'bg-slate-100 text-[var(--color-text-2)]'
                }`}
            >
              1
            </div>
            <div className="flex min-h-7 flex-col justify-center">
              <div className="text-[15px] font-semibold">{t('system.user.userSyncPage.basicConfig')}</div>
              <div className="mt-1 text-[12px] text-[var(--color-text-3)]">
                {t('system.user.userSyncPage.basicConfigDesc')}
              </div>
            </div>
          </div>
        </button>

        <button
          type="button"
          className={`rounded-2xl border px-4 py-3 text-left transition ${currentStep === 2 ? 'border-[var(--color-primary)] bg-blue-50' : 'border-[var(--color-border)] bg-white'
            }`}
          onClick={() => {
            if (currentStep === 1) {
              handleNextStep();
              return;
            }
            setCurrentStep(2);
          }}
        >
          <div className="flex items-center gap-3">
            <div
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[13px] ${currentStep === 2 ? 'bg-[var(--color-primary)] text-white' : 'bg-slate-100 text-[var(--color-text-2)]'
                }`}
            >
              2
            </div>
            <div className="flex min-h-7 flex-col justify-center">
              <div className="text-[15px] font-semibold">{t('system.user.userSyncPage.accessConfig')}</div>
              <div className="mt-1 text-[12px] text-[var(--color-text-3)]">
                {t('system.user.userSyncPage.accessConfigDesc')}
              </div>
            </div>
          </div>
        </button>
      </div>

      <div className="mt-5 rounded-[22px] border border-[var(--color-border)] bg-white px-5 py-5">
        <Form form={form} layout="vertical">
          {currentStep === 1 ? (
            <>
              <div className="mb-4 text-[18px] font-semibold">{t('system.user.userSyncPage.basicConfig')}</div>
              <Form.Item
                name="name"
                label={t('common.name')}
                rules={[{ required: true, whitespace: true }]}
              >
                <Input placeholder={t(`common.inputMsg`)} />
              </Form.Item>
              <Form.Item
                name="integration_instance"
                label={t('system.user.userSyncPage.integrationSystem')}
                rules={[{ required: true }]}
              >
                <Select
                  placeholder={t('system.user.userSyncPage.integrationSystemPlaceholder')}
                  options={instanceOptions}
                />
              </Form.Item>
              <Form.Item
                name="root_group_name"
                label={t('system.user.userSyncPage.rootGroupNameLabel')}
                rules={[{ required: true, whitespace: true }]}
                extra={
                  (<div className="ml-2 text-xs text-[var(--color-text-3)]">
                    {t('system.user.userSyncPage.rootGroupHelp')}
                  </div>)
                }
              >
                <Input
                  placeholder={t('common.inputMsg')}
                />
              </Form.Item>
              <Form.Item name="description" label={t('system.user.userSyncPage.description')}>
                <Input.TextArea rows={4} placeholder={t('common.inputMsg')} />
              </Form.Item>
            </>
          ) : (
            <UserSyncConfigFields
              selectedInstanceId={selectedInstanceId}
              providersLoading={providersLoading}
              resolvedTemplate={resolvedTemplate}
              mappingRows={mappingRows}
              t={t}
              onMappingRowsChange={setMappingRows}
            />
          )}
        </Form>
      </div>
    </OperateModal>
  );
};

export default UserSyncOperateModal;
