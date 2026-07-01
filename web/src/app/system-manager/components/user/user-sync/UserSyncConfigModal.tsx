import React, { useEffect, useMemo, useState } from 'react';
import { Button, Form } from 'antd';

import OperateModal from '@/components/operate-modal';
import type { ProviderManifest } from '@/app/system-manager/types/integration-center';
import type { AvailableInstance, UserSyncSource, UserSyncSourceConfigFormValues } from '@/app/system-manager/types/user-sync';
import {
  getWriteOnlyKeys,
  getEffectiveRootDepartmentFieldKey,
  mergeUserSyncBusinessConfigWithDefaults,
  resolveUserSyncTemplate,
} from '@/app/system-manager/utils/userSyncUtils';
import { type MappingRow, toMappingRows } from '@/app/system-manager/utils/userSyncPageUtils';
import UserSyncConfigFields from '@/app/system-manager/components/user/user-sync/UserSyncConfigFields';

interface UserSyncConfigModalProps {
  open: boolean;
  source: UserSyncSource | null;
  loading: boolean;
  previewLoading: boolean;
  availableInstances: AvailableInstance[];
  providers: ProviderManifest[];
  providersLoading: boolean;
  t: (key: string, fallback?: string) => string;
  onClose: () => void;
  onPreview: (values: UserSyncSourceConfigFormValues, mappingRows: MappingRow[], writeOnlyKeys: Set<string>) => void;
  onSubmit: (values: UserSyncSourceConfigFormValues, mappingRows: MappingRow[]) => void;
}

const UserSyncConfigModal: React.FC<UserSyncConfigModalProps> = ({
  open,
  source,
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
  const [form] = Form.useForm<UserSyncSourceConfigFormValues>();
  const [mappingRows, setMappingRows] = useState<MappingRow[]>(toMappingRows({}));

  const resolvedTemplate = useMemo(
    () => resolveUserSyncTemplate(source?.integration_instance, availableInstances, providers),
    [source?.integration_instance, availableInstances, providers],
  );
  const rootScopeFieldKey = useMemo(
    () => getEffectiveRootDepartmentFieldKey(source, resolvedTemplate),
    [resolvedTemplate, source],
  );

  useEffect(() => {
    if (!open || !source) return;
    form.resetFields();
    form.setFieldsValue({
      business_config: mergeUserSyncBusinessConfigWithDefaults(
        source.business_config || {},
        resolvedTemplate,
        { excludeRootScope: true, rootScopeFieldKey },
      ),
    });
    setMappingRows(toMappingRows(source.field_mapping));
  }, [open, resolvedTemplate, rootScopeFieldKey, source, form]);

  const writeOnlyKeys = useMemo(() => getWriteOnlyKeys(resolvedTemplate), [resolvedTemplate]);

  const handleSubmit = async () => {
    try {
      await form.validateFields();
    } catch {
      return;
    }
    onSubmit(form.getFieldsValue(true) as UserSyncSourceConfigFormValues, mappingRows);
  };

  const handlePreview = async () => {
    try {
      await form.validateFields();
    } catch {
      return;
    }
    onPreview(form.getFieldsValue(true) as UserSyncSourceConfigFormValues, mappingRows, writeOnlyKeys);
  };

  return (
    <OperateModal
    title={t('system.user.userSyncPage.accessConfig')}
    subTitle={source ? `${source.name}` : ''}
    open={open}
    onCancel={onClose}
    width={820}
    footer={(
      <div className="flex justify-end gap-2">
        <Button onClick={onClose} disabled={loading || previewLoading}>
          {t('common.cancel')}
        </Button>
        <Button onClick={handlePreview} loading={previewLoading} disabled={loading}>
          {t('system.integrationCenter.testConnection')}
        </Button>
        <Button type="primary" onClick={handleSubmit} loading={loading} disabled={previewLoading}>
          {t('common.save')}
        </Button>
      </div>
    )}
    destroyOnClose
  >
    <Form form={form} layout="vertical">
      <UserSyncConfigFields
        selectedInstanceId={source?.integration_instance}
        providersLoading={providersLoading}
        resolvedTemplate={resolvedTemplate}
        mappingRows={mappingRows}
        t={t}
        onMappingRowsChange={setMappingRows}
        rootScopeField={source?.root_scope_field}
      />
    </Form>
  </OperateModal>
  );
};

export default UserSyncConfigModal;
