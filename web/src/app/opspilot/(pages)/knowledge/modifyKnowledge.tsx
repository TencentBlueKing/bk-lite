import React, { useEffect, useState } from 'react';
import { Form } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import CommonForm from '@/app/opspilot/components/knowledge/commonForm';
import { ModifyKnowledgeModalProps, ModelOption } from '@/app/opspilot/types/knowledge';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

const ModifyKnowledgeModal: React.FC<ModifyKnowledgeModalProps> = ({ visible, onCancel, onConfirm, initialValues, isTraining }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { fetchEmbeddingModels } = useKnowledgeApi();
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const [originalEmbedModel, setOriginalEmbedModel] = useState<number | null>(null);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [modalContent, setModalContent] = useState('');
  const [modalLoading, setModalLoading] = useState(false);

  useEffect(() => {
    const fetchModels = async () => {
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
        const defaultValues: any = {};
        if (modelOptions.length > 0) {
          defaultValues.embed_model = modelOptions.filter(option => option.enabled)?.[0]?.id;
        }
        form.setFieldsValue(defaultValues);
      }
    });
  }, [initialValues, form, modelOptions, visible]);

  const handleConfirm = async () => {
    try {
      setConfirmLoading(true);
      const values = await form.validateFields();
      if (initialValues && values.embed_model !== originalEmbedModel) {
        setModalContent(t('knowledge.embeddingModelTip'));
        setIsModalVisible(true);
      } else {
        await onConfirm(values);
        form.resetFields();
        setConfirmLoading(false);
      }
    } catch {
      setConfirmLoading(false);
    }
  };

  const handleModalOk = async () => {
    try {
      setModalLoading(true);
      const values = await form.validateFields();
      await onConfirm(values);
      form.resetFields();
    } finally {
      setModalLoading(false);
      setConfirmLoading(false);
      setIsModalVisible(false);
    }
  };

  const handleModalCancel = () => {
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
        onOk={handleModalOk}
        onCancel={handleModalCancel}
        confirmLoading={modalLoading}
        centered
      >
        <p>{modalContent}</p>
      </OperateModal>
    </>
  );
};

export default ModifyKnowledgeModal;
