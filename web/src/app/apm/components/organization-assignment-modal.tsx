'use client';

import { useEffect } from 'react';
import { Alert, Form, Modal } from 'antd';
import GroupTreeSelect from '@/components/group-tree-select';

interface OrganizationAssignmentModalProps {
  open: boolean;
  title: string;
  organizationIds: number[];
  submitting?: boolean;
  description?: string;
  onCancel: () => void;
  onSubmit: (organizationIds: number[]) => Promise<void> | void;
}

export default function OrganizationAssignmentModal({
  open,
  title,
  organizationIds,
  submitting = false,
  description,
  onCancel,
  onSubmit,
}: OrganizationAssignmentModalProps) {
  const [form] = Form.useForm<{ organization_ids: number[] }>();
  const organizationKey = organizationIds.join(',');

  useEffect(() => {
    if (open) form.setFieldsValue({ organization_ids: organizationIds });
  }, [form, open, organizationKey]);

  return (
    <Modal
      title={title}
      open={open}
      okText="保存"
      cancelText="取消"
      confirmLoading={submitting}
      afterOpenChange={(visible) => {
        // destroyOnHidden + preserve={false} 会在弹窗关闭时卸载字段；待字段重新
        // 挂载后再同步一次，避免已有组织在下拉中显示为空而被误覆盖。
        if (visible) form.setFieldsValue({ organization_ids: organizationIds });
      }}
      onOk={() => form.submit()}
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        preserve={false}
        onFinish={(values) => onSubmit(values.organization_ids)}
      >
        <Form.Item name="organization_ids" label="可用组织" rules={[{ required: true, message: '请至少选择一个组织' }]}>
          <GroupTreeSelect multiple mode="ownership" showSearch placeholder="选择组织" />
        </Form.Item>
        {description ? <Alert type="info" showIcon message={description} /> : null}
      </Form>
    </Modal>
  );
}
