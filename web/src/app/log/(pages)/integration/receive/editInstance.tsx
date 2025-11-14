'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useMemo,
} from 'react';
import { Button, Form, message, Input } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import useLogApi from '@/app/log/api/integration';
import { ModalRef, ModalProps } from '@/app/log/types';
import { InstanceInfo } from '@/app/log/types/integration';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelector from '@/components/group-tree-select';
import { cloneDeep } from 'lodash';

const EditInstance = forwardRef<ModalRef, ModalProps>(({ onSuccess }, ref) => {
  const { updateMonitorInstance, setInstancesGroup } = useLogApi();
  const { t } = useTranslation();
  const formRef = useRef<FormInstance>(null);
  const [visible, setVisible] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [configForm, setConfigForm] = useState<InstanceInfo>({});
  const [title, setTitle] = useState<string>('');
  const [modalType, setModalType] = useState<string>('');

  const isEdit = useMemo(() => {
    return modalType === 'edit';
  }, [modalType]);

  useImperativeHandle(ref, () => ({
    showModal: ({ title, form, type }) => {
      // 开启弹窗的交互
      setTitle(title);
      setModalType(type);
      setConfigForm(cloneDeep(form));
      setVisible(true);
    },
  }));

  useEffect(() => {
    if (visible) {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({
        name: configForm.name,
        organizations: (configForm.organization || []).map((item) =>
          Number(item)
        ),
      });
    }
  }, [visible, configForm]);

  const handleOperate = async (params: any) => {
    try {
      setConfirmLoading(true);
      const request = isEdit ? updateMonitorInstance : setInstancesGroup;
      await request(params);
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
      let params = { ...values, instance_id: configForm.id };
      if (!isEdit) {
        params = {
          instance_ids: configForm.keys,
          organizations: values.organizations,
        };
      }
      handleOperate(params);
    });
  };

  const handleCancel = () => {
    setVisible(false);
  };

  return (
    <div>
      <OperateModal
        width={600}
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
          {isEdit && (
            <Form.Item<InstanceInfo>
              label={t('log.integration.instanceName')}
              name="name"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Input />
            </Form.Item>
          )}
          <Form.Item<InstanceInfo>
            label={t('log.group')}
            name="organizations"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <GroupTreeSelector />
          </Form.Item>
        </Form>
      </OperateModal>
    </div>
  );
});
EditInstance.displayName = 'EditInstance';
export default EditInstance;
