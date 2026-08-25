'use client';

import { useEffect } from 'react';
import { Alert, Form, Modal } from 'antd';
import GroupTreeSelect from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';

interface OrganizationAssignmentModalProps {
  open: boolean;
  title: string;
  organizationIds: number[];
  submitting?: boolean;
  description?: string;
  onCancel: () => void;
  onSubmit: (organizationIds: number[]) => Promise<void> | void;
}

export default function OrganizationAssignmentModal(props: OrganizationAssignmentModalProps) {
  if (!props.open) return null;
  return <OpenOrganizationAssignmentModal {...props} />;
}

function OpenOrganizationAssignmentModal({
  open,
  title,
  organizationIds,
  submitting = false,
  description,
  onCancel,
  onSubmit,
}: OrganizationAssignmentModalProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<{ organization_ids: number[] }>();
  const organizationKey = organizationIds.join(',');

  useEffect(() => {
    if (open) form.setFieldsValue({ organization_ids: organizationIds });
  }, [form, open, organizationKey]);

  return (
    <Modal
      title={title}
      open={open}
      okText={t('common.save', '保存')}
      cancelText={t('common.cancel', '取消')}
      confirmLoading={submitting}
      styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }}
      afterOpenChange={(visible) => {
        // 弹窗过渡完成后再同步一次，避免已有组织在下拉中显示为空而被误覆盖。
        if (visible) form.setFieldsValue({ organization_ids: organizationIds });
      }}
      onOk={() => form.submit()}
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
    >
      <Form
        form={form}
        layout="vertical"
        preserve={false}
        onFinish={(values) => onSubmit(values.organization_ids)}
      >
        <Form.Item name="organization_ids" label={t('apm.common.organizations', '可用组织')} rules={[{ required: true, message: t('apm.common.organizationRequired', '请至少选择一个组织') }]}>
          <GroupTreeSelect multiple mode="ownership" showSearch placeholder={t('apm.common.selectOrganization', '选择组织')} />
        </Form.Item>
        {description ? <Alert type="info" showIcon message={description} /> : null}
      </Form>
    </Modal>
  );
}
