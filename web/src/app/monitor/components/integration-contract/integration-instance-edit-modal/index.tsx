'use client';

import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Form, Input, message } from 'antd';
import type { FormInstance } from 'antd';
import { cloneDeep } from 'lodash';
import GroupTreeSelector from '@/components/group-tree-select';
import OperateFormModal from '@/components/operate-form-modal';
import { useTranslation } from '@/utils/i18n';

export interface IntegrationInstanceEditModalForm {
  organization?: Array<string | number>;
  organizations?: Array<string | number>;
  keys?: React.Key[];
  [key: string]: unknown;
}

export interface IntegrationInstanceEditModalValues {
  name?: string;
  organizations: Array<string | number>;
}

export interface IntegrationInstanceEditModalConfig {
  title: string;
  type: string;
  form: IntegrationInstanceEditModalForm;
}

export interface IntegrationInstanceEditModalRef {
  showModal: (config: IntegrationInstanceEditModalConfig) => void;
}

interface IntegrationInstanceEditModalProps {
  onSuccess: () => void;
  nameLabel: string;
  groupLabel: string;
  getInstanceName: (
    configForm: IntegrationInstanceEditModalForm
  ) => string | undefined;
  submitEdit: (context: {
    sourceForm: IntegrationInstanceEditModalForm;
    values: IntegrationInstanceEditModalValues;
  }) => Promise<unknown>;
  submitBatch: (context: {
    sourceForm: IntegrationInstanceEditModalForm;
    values: IntegrationInstanceEditModalValues;
  }) => Promise<unknown>;
}

const IntegrationInstanceEditModal = forwardRef<
  IntegrationInstanceEditModalRef,
  IntegrationInstanceEditModalProps
>(
  (
    {
      onSuccess,
      nameLabel,
      groupLabel,
      getInstanceName,
      submitEdit,
      submitBatch,
    },
    ref
  ) => {
    const { t } = useTranslation();
    const formRef = useRef<FormInstance>(null);
    const [visible, setVisible] = useState(false);
    const [confirmLoading, setConfirmLoading] = useState(false);
    const [configForm, setConfigForm] =
      useState<IntegrationInstanceEditModalForm>({});
    const [title, setTitle] = useState('');
    const [modalType, setModalType] = useState('');

    const isEdit = useMemo(() => modalType === 'edit', [modalType]);

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form, type }) => {
        setTitle(title);
        setModalType(type);
        setConfigForm(cloneDeep(form));
        setVisible(true);
      },
    }));

    useEffect(() => {
      if (!visible) {
        return;
      }

      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({
        name: getInstanceName(configForm),
        organizations: (configForm.organization || []).map((item) =>
          Number(item)
        ),
      });
    }, [configForm, getInstanceName, visible]);

    const handleCancel = () => {
      setVisible(false);
    };

    const handleOperate = async (values: IntegrationInstanceEditModalValues) => {
      try {
        setConfirmLoading(true);
        if (isEdit) {
          await submitEdit({
            sourceForm: configForm,
            values,
          });
        } else {
          await submitBatch({
            sourceForm: configForm,
            values,
          });
        }
        message.success(t('common.successfullyModified'));
        handleCancel();
        onSuccess();
      } catch (error) {
        console.error(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        handleOperate(values as IntegrationInstanceEditModalValues);
      });
    };

    return (
      <OperateFormModal
        width={600}
        title={title}
        visible={visible}
        onCancel={handleCancel}
        confirmText={t('common.confirm')}
        cancelText={t('common.cancel')}
        confirmLoading={confirmLoading}
        onConfirm={handleSubmit}
      >
        <Form ref={formRef} name="integration-instance-edit" layout="vertical">
          {isEdit && (
            <Form.Item
              label={nameLabel}
              name="name"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Input />
            </Form.Item>
          )}
          <Form.Item
            label={groupLabel}
            name="organizations"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <GroupTreeSelector />
          </Form.Item>
        </Form>
      </OperateFormModal>
    );
  }
);

IntegrationInstanceEditModal.displayName = 'IntegrationInstanceEditModal';

export default IntegrationInstanceEditModal;
