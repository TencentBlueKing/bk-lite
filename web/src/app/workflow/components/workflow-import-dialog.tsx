'use client';

import { UploadOutlined } from '@ant-design/icons';
import { App, Button, Form, Upload } from 'antd';
import type { UploadFile } from 'antd';
import { useEffect, useState } from 'react';

import GroupTreeSelect from '@/components/group-tree-select';
import OperateModal from '@/components/operate-modal';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';
import { WorkflowPermission } from './workflow-permission';

const PACK_LIMIT_BYTES = 200 * 1024 * 1024;

export function WorkflowImportDialog({
  open,
  confirmLoading,
  onCancel,
  onSubmit,
}: {
  open: boolean;
  confirmLoading: boolean;
  onCancel: () => void;
  onSubmit: (value: { team: number[]; file: File }) => void;
}) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const { selectedGroup } = useUserInfoContext();
  const [form] = Form.useForm<{ team: number[] }>();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const team = Form.useWatch('team', form);
  const selectedFile = fileList[0]?.originFileObj;
  const ready = Array.isArray(team) && team.length > 0 && selectedFile instanceof File;

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({ team: selectedGroup?.id ? [Number(selectedGroup.id)] : [] });
    setFileList([]);
  }, [form, open, selectedGroup?.id]);

  const submit = () => {
    if (!ready || !selectedFile) return;
    form.validateFields().then((values) => onSubmit({ team: values.team, file: selectedFile })).catch(() => undefined);
  };

  return (
    <OperateModal
      title={t('workflowOrchestration.workflow.import', '导入')}
      open={open}
      confirmLoading={confirmLoading}
      okText={t('common.confirm', '确定')}
      cancelText={t('common.cancel', '取消')}
      styles={{ footer: { marginTop: 20 } }}
      destroyOnHidden
      onCancel={onCancel}
      footer={(
        <div className="flex justify-end gap-2">
          <Button disabled={confirmLoading} onClick={onCancel}>{t('common.cancel', '取消')}</Button>
          <WorkflowPermission operation="Add">
            <Button type="primary" disabled={!ready} loading={confirmLoading} onClick={submit}>{t('common.confirm', '确定')}</Button>
          </WorkflowPermission>
        </div>
      )}
    >
      <Form form={form} layout="vertical" requiredMark>
        <Form.Item
          name="team"
          label={t('workflowOrchestration.workflow.organization', '组织')}
          rules={[{ required: true, type: 'array', min: 1, message: t('workflowOrchestration.workflow.organizationRequired', '请选择组织') }]}
        >
          <GroupTreeSelect multiple placeholder={t('workflowOrchestration.workflow.organizationRequired', '请选择组织')} />
        </Form.Item>
        <Form.Item label={t('workflowOrchestration.workflow.importPack', '流程压缩包')} required>
          <Upload
            accept=".zip,application/zip"
            maxCount={1}
            fileList={fileList}
            beforeUpload={(file) => {
              if (!file.name.toLowerCase().endsWith('.zip')) {
                message.warning(t('workflowOrchestration.workflow.importFileInvalid', '请选择 zip 压缩包'));
                return Upload.LIST_IGNORE;
              }
              if (file.size > PACK_LIMIT_BYTES) {
                message.error(t('workflowOrchestration.workflow.importPackTooLarge', '流程压缩包不能超过 200MB'));
                return Upload.LIST_IGNORE;
              }
              setFileList([{ uid: file.uid, name: file.name, size: file.size, status: 'done', originFileObj: file }]);
              return Upload.LIST_IGNORE;
            }}
            onRemove={() => {
              setFileList([]);
              return true;
            }}
          >
            <Button icon={<UploadOutlined />}>{t('workflowOrchestration.workflow.importPackChoose', '选择压缩包')}</Button>
          </Upload>
        </Form.Item>
      </Form>
    </OperateModal>
  );
}
