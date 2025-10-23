import React, { useEffect, useState, ReactNode } from 'react';
import { Form, Button } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import CommonForm from '@/app/opspilot/components/knowledge/commonForm';
import { ModifyKnowledgeModalProps, ModelOption } from '@/app/opspilot/types/knowledge';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

const ModifyKnowledgeModal: React.FC<ModifyKnowledgeModalProps> = ({ 
  visible, 
  onCancel, 
  onConfirm, 
  initialValues, 
  isTraining 
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { fetchEmbeddingModels } = useKnowledgeApi();
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const [originalEmbedModel, setOriginalEmbedModel] = useState<number | null>(null);
  const [isModalVisible, setIsModalVisible] = useState<boolean>(false);
  const [modalContent, setModalContent] = useState<ReactNode>('');
  const [modalLoading, setModalLoading] = useState<boolean>(false);

  useEffect(() => {
    const fetchModels = async (): Promise<void> => {
      try {
        const data = await fetchEmbeddingModels();
        setModelOptions(data);
      } catch (error) {
        console.error(`${t('common.fetchFailed')}:`, error);
      }
    };

    fetchModels();
  }, []);

  useEffect(() => {
    if (!visible) return;

    Promise.resolve().then(() => {
      if (initialValues) {
        form.setFieldsValue(initialValues);
        setOriginalEmbedModel(initialValues.embed_model);
      } else {
        form.resetFields();
        const defaultValues: Record<string, any> = {};
        if (modelOptions.length > 0) {
          const enabledOption = modelOptions.find(option => option.enabled);
          if (enabledOption) {
            defaultValues.embed_model = enabledOption.id;
          }
        }
        form.setFieldsValue(defaultValues);
      }
    });
  }, [initialValues, form, modelOptions, visible]);

  const handleConfirm = async (): Promise<void> => {
    try {
      setConfirmLoading(true);
      const values = await form.validateFields();
      if (initialValues && values.embed_model !== originalEmbedModel) {
        // 显示带有三个按钮的确认对话框
        setModalContent(
          <div className="space-y-3">
            <p>{t('knowledge.embeddingModelTip')}</p>
            <div className="bg-orange-50 p-3 rounded border border-orange-200">
              <p className="text-orange-800 text-sm mb-2 font-medium">
                {t('knowledge.embeddingModelWarning')}
              </p>
              <p className="text-gray-700 text-sm">
                {t('knowledge.embeddingModelOptions')}
              </p>
            </div>
          </div>
        );
        setIsModalVisible(true);
      } else {
        await onConfirm(values);
        form.resetFields();
        setConfirmLoading(false);
      }
    } catch (error) {
      console.error('Form validation failed:', error);
      setConfirmLoading(false);
    }
  };

  const handleEmbedModelConfirm = async (deleteQaPairs: boolean): Promise<void> => {
    try {
      setModalLoading(true);
      const values = await form.validateFields();
      // 添加delete_qa_pairs字段
      const submitValues = {
        ...values,
        delete_qa_pairs: deleteQaPairs
      };
      await onConfirm(submitValues);
      form.resetFields();
    } catch (error) {
      console.error('Failed to submit form:', error);
    } finally {
      setModalLoading(false);
      setConfirmLoading(false);
      setIsModalVisible(false);
    }
  };

  const handleModalCancel = (): void => {
    setConfirmLoading(false);
    setIsModalVisible(false);
  };

  return (
    <>
      <OperateModal
        visible={visible}
        title={initialValues ? t('common.edit') : t('common.add')}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        onCancel={onCancel}
        onOk={handleConfirm}
        confirmLoading={confirmLoading}
      >
        <CommonForm
          form={form}
          modelOptions={modelOptions}
          isTraining={isTraining}
          formType="knowledge"
          visible={visible}
        />
      </OperateModal>
      <OperateModal
        title={t('common.confirm')}
        visible={isModalVisible}
        onCancel={handleModalCancel}
        confirmLoading={modalLoading}
        centered
        width={520}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={handleModalCancel}>
              {t('common.cancel')}
            </Button>
            <Button 
              type="default" 
              onClick={() => handleEmbedModelConfirm(true)}
              loading={modalLoading}
            >
              {t('knowledge.documents.deleteQaPairs')}
            </Button>
            <Button 
              type="primary" 
              onClick={() => handleEmbedModelConfirm(false)}
              loading={modalLoading}
            >
              {t('knowledge.documents.keepQaPairs')}
            </Button>
          </div>
        }
      >
        {modalContent}
      </OperateModal>
    </>
  );
};

export default ModifyKnowledgeModal;
