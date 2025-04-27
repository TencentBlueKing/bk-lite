'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from 'react';
import { Button, Form, message } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import useApiClient from '@/utils/request';
import { ModalRef } from '@/app/monitor/types';
import { NodeConfigInfo } from '@/app/monitor/types/monitor';
import { useTranslation } from '@/utils/i18n';
import { deepClone } from '@/app/monitor/utils/common';
import CodeEditor from '@/app/monitor/components/codeEditor';

interface ModalProps {
  onSuccess: () => void;
}

const EditConfig = forwardRef<ModalRef, ModalProps>(({ onSuccess }, ref) => {
  const { post } = useApiClient();
  const { t } = useTranslation();
  const formRef = useRef<FormInstance>(null);
  const [visible, setVisible] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [configForm, setConfigForm] = useState<NodeConfigInfo>({});
  const [title, setTitle] = useState<string>('');

  useImperativeHandle(ref, () => ({
    showModal: ({ title, form }) => {
      // 开启弹窗的交互
      setTitle(title);
      setConfigForm(deepClone(form));
      setVisible(true);
    },
  }));

  useEffect(() => {
    if (visible) {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({
        content: configForm.content,
        id: configForm.config_id,
      });
    }
  }, [visible, configForm]);

  const operateGroup = async (params: NodeConfigInfo) => {
    try {
      setConfirmLoading(true);
      await post(
        '/monitor/api/node_mgmt/update_instance_child_config/',
        params
      );
      message.success(t('common.successfullyModified'));
      handleCancel();
      onSuccess();
    } catch (error) {
      console.log(error);
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleSubmit = () => {
    formRef.current?.validateFields().then((values) => {
      operateGroup({
        ...values,
        id: configForm.config_id,
      });
    });
  };

  const handleCancel = () => {
    setVisible(false);
  };

  return (
    <div>
      <OperateModal
        width={800}
        title={title}
        visible={visible}
        onCancel={handleCancel}
        footer={
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              loading={confirmLoading}
              onClick={handleSubmit}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <Form ref={formRef} name="basic" layout="vertical">
          <Form.Item<NodeConfigInfo>
            label={t('monitor.intergrations.configuration')}
            name="content"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <CodeEditor
              mode="python"
              theme="monokai"
              name="editor"
              width="100%"
              height="300px"
            />
          </Form.Item>
        </Form>
      </OperateModal>
    </div>
  );
});
EditConfig.displayName = 'EditConfig';
export default EditConfig;
