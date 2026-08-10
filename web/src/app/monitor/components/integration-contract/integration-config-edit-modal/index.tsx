'use client';

import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from 'react';
import { Form, Spin, message } from 'antd';
import type { FormInstance } from 'antd';
import { cloneDeep } from 'lodash';
import CompactEmptyState from '@/components/compact-empty-state';
import OperateFormModal from '@/components/operate-form-modal';
import { useTranslation } from '@/utils/i18n';

export interface IntegrationConfigEditModalFormData {
  [key: string]: unknown;
}

export interface IntegrationConfigEditModalConfig {
  title: string;
  form: IntegrationConfigEditModalFormData;
}

export interface IntegrationConfigEditModalRef {
  showModal: (config: IntegrationConfigEditModalConfig) => void;
}

interface IntegrationConfigEditModalRenderContext {
  form: FormInstance;
  sourceForm: IntegrationConfigEditModalFormData;
  loadedConfig: unknown;
}

interface IntegrationConfigEditModalProps {
  onSuccess: () => void;
  width?: number;
  zIndex?: number;
  emptyDescription?: string;
  loadConfig: (
    sourceForm: IntegrationConfigEditModalFormData
  ) => Promise<unknown>;
  getFormItems: (
    context: IntegrationConfigEditModalRenderContext
  ) => React.ReactNode;
  getDefaultValues: (
    context: Omit<IntegrationConfigEditModalRenderContext, 'form'>
  ) => Record<string, unknown>;
  submitConfig: (context: {
    sourceForm: IntegrationConfigEditModalFormData;
    loadedConfig: unknown;
    values: Record<string, unknown>;
  }) => Promise<unknown>;
}

const IntegrationConfigEditModal = forwardRef<
  IntegrationConfigEditModalRef,
  IntegrationConfigEditModalProps
>(
  (
    {
      onSuccess,
      width = 600,
      zIndex,
      emptyDescription,
      loadConfig,
      getFormItems,
      getDefaultValues,
      submitConfig,
    },
    ref
  ) => {
    const [form] = Form.useForm();
    const { t } = useTranslation();
    const [confirmLoading, setConfirmLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [title, setTitle] = useState('');
    const [sourceForm, setSourceForm] =
      useState<IntegrationConfigEditModalFormData>({});
    const [loadedConfig, setLoadedConfig] = useState<unknown>(null);
    const [configLoading, setConfigLoading] = useState(false);

    useImperativeHandle(ref, () => ({
      showModal: ({ form, title }) => {
        setSourceForm(cloneDeep(form));
        setTitle(title);
        setModalVisible(true);
        setConfirmLoading(false);
      },
    }));

    useEffect(() => {
      if (!modalVisible) {
        return;
      }

      let cancelled = false;

      const run = async () => {
        setConfigLoading(true);
        try {
          const data = await loadConfig(sourceForm);
          if (!cancelled) {
            setLoadedConfig(data);
          }
        } finally {
          if (!cancelled) {
            setConfigLoading(false);
          }
        }
      };

      run();

      return () => {
        cancelled = true;
      };
    }, [loadConfig, modalVisible, sourceForm]);

    const formItems = useMemo(() => {
      if (configLoading) {
        return null;
      }

      return getFormItems({
        form,
        sourceForm,
        loadedConfig,
      });
    }, [configLoading, form, getFormItems, loadedConfig, sourceForm]);

    useEffect(() => {
      if (configLoading || !modalVisible) {
        return;
      }

      const values = getDefaultValues({
        sourceForm,
        loadedConfig,
      });
      form.resetFields();
      form.setFieldsValue(values);
    }, [
      configLoading,
      form,
      getDefaultValues,
      loadedConfig,
      modalVisible,
      sourceForm,
    ]);

    const handleCancel = () => {
      form.resetFields();
      setModalVisible(false);
      setConfigLoading(false);
      setLoadedConfig(null);
      setSourceForm({});
    };

    const handleSubmit = () => {
      form.validateFields().then(async (values) => {
        try {
          setConfirmLoading(true);
          await submitConfig({
            sourceForm,
            loadedConfig,
            values,
          });
          message.success(t('common.successfullyModified'));
          handleCancel();
          onSuccess();
        } catch (error: any) {
          message.error(error?.message || t('common.operationFailed'));
        } finally {
          setConfirmLoading(false);
        }
      });
    };

    const shouldShowEmpty =
      !configLoading &&
      !!emptyDescription &&
      !React.Children.count(formItems);

    return (
      <OperateFormModal
        width={width}
        title={title}
        visible={modalVisible}
        zIndex={zIndex}
        onCancel={handleCancel}
        confirmText={t('common.confirm')}
        cancelText={t('common.cancel')}
        confirmLoading={confirmLoading}
        confirmDisabled={configLoading || shouldShowEmpty}
        onConfirm={handleSubmit}
      >
        <div className="px-[10px]">
          <Spin spinning={configLoading} className="w-full">
            <div style={{ minHeight: configLoading ? '200px' : 'auto' }}>
              {shouldShowEmpty ? (
                <CompactEmptyState description={emptyDescription} className="py-8" />
              ) : (
                <Form form={form} name="integration-config-edit" layout="vertical">
                  {formItems}
                </Form>
              )}
            </div>
          </Spin>
        </div>
      </OperateFormModal>
    );
  }
);

IntegrationConfigEditModal.displayName = 'IntegrationConfigEditModal';

export default IntegrationConfigEditModal;
