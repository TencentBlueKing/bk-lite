'use client';

import React, { useState, useEffect, forwardRef, useImperativeHandle, useRef } from 'react';
import { Form, Select, InputNumber, Input, message, Spin, Tag, Button, Space } from 'antd';
import { RobotOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import { useSkillApi } from '@/app/opspilot/api/skill';
import OperateModal from '@/components/operate-modal';
import type {
  GenerateQAPairModalProps,
  ModalRef,
  DocumentInfo,
  ChunkItem
} from '@/app/opspilot/types/knowledge';

const { TextArea } = Input;

interface FormData {
  questionLlmModel: number;
  answerLlmModel: number;
  qaCount: number;
  questionPrompt: string;
  answerPrompt: string;
}

const GenerateQAPairModal = forwardRef<ModalRef, GenerateQAPairModalProps>(
  ({ onSuccess }, ref) => {
    const [form] = Form.useForm();
    const { t } = useTranslation();
    const { createQAPairsByChunk, getInstanceDetail } = useKnowledgeApi();
    const { fetchLlmModels: fetchLlmModelsApi } = useSkillApi();

    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [loading, setLoading] = useState<boolean>(false);
    const [llmModelsLoading, setLlmModelsLoading] = useState<boolean>(false);
    const [llmModels, setLlmModels] = useState<any[]>([]);
    const [documentId, setDocumentId] = useState<string>('');
    const [selectedChunkIds, setSelectedChunkIds] = useState<string[]>([]);
    const [selectedChunks, setSelectedChunks] = useState<ChunkItem[]>([]);
    const [documentInfo, setDocumentInfo] = useState<DocumentInfo | null>(null);

    const formRef = useRef<FormData>({
      questionLlmModel: 0,
      answerLlmModel: 0,
      qaCount: 1,
      questionPrompt: '',
      answerPrompt: ''
    });

    const fetchDocumentDetail = async (docId: string) => {
      try {
        setLoading(true);
        const detail = await getInstanceDetail(parseInt(docId));
        console.log('Document detail fetched:', detail);
        setDocumentInfo(detail);
      } catch (error) {
        console.error('Failed to fetch document detail:', error);
        message.error(t('knowledge.qaPairs.fetchDocumentsListFailed'));
      } finally {
        setLoading(false);
      }
    };

    useImperativeHandle(ref, () => ({
      showModal: ({ documentId, selectedChunkIds = [], selectedChunks = [] }) => {
        setDocumentId(documentId);
        setSelectedChunkIds(selectedChunkIds);
        setSelectedChunks(selectedChunks);
        setVisible(true);
        
        // 打开弹窗时立即获取文档详情
        if (documentId) {
          fetchDocumentDetail(documentId);
        }
        
        // 重置表单到默认值
        form.resetFields();
        formRef.current = {
          questionLlmModel: 0,
          answerLlmModel: 0,
          qaCount: 1,
          questionPrompt: '',
          answerPrompt: ''
        };
      }
    }));

    // 获取LLM模型列表
    const fetchLlmModels = async () => {
      setLlmModelsLoading(true);
      try {
        const models = await fetchLlmModelsApi();
        setLlmModels(models);
        
        // 设置默认模型和提示语
        if (models.length > 0) {
          const defaultValues = {
            questionLlmModel: models[0].id,
            answerLlmModel: models[0].id,
            qaCount: 1,
            questionPrompt: '请根据我提供的文本内容，生成与其紧密相关的问题，要求如下：\n1、仔细阅读并理解整段文本（该文本为长文档的一个分块）。\n2、从文本中提炼3-5个关键信息点，并据此生成问题。\n3、问题应涵盖主要事实、细节、原因、影响等，不要集中在单一方面。\n4、问题必须基于原文内容，不能引入不存在或推测性的信息。\n5、问题应简洁、明确、完整，不带有"根据本文"或"文中提到"等表述。\n6、仅输出问题列表，每行一个，不附加答案。',
            answerPrompt: '请根据我提供的文本和相应问题列表，生成每个问题的答案，要求如下：\n1、仔细阅读文本，逐一回答问题。\n2、答案必须严格基于源文信息，不能编造或添加未提及内容。\n3、保持客观中立，避免主观评价或情感化表达。\n4、每个答案应完整且清晰。'
          };
          form.setFieldsValue(defaultValues);
          formRef.current = defaultValues;
        }
      } catch {
        message.error(t('common.fetchFailed'));
      } finally {
        setLlmModelsLoading(false);
      }
    };

    useEffect(() => {
      if (visible) {
        fetchLlmModels();
      }
    }, [visible]);

    // 处理表单值变化
    const handleFormValuesChange = (changedValues: any, allValues: FormData) => {
      formRef.current = {
        questionLlmModel: allValues.questionLlmModel || 0,
        answerLlmModel: allValues.answerLlmModel || 0,
        qaCount: allValues.qaCount || 1,
        questionPrompt: allValues.questionPrompt || '',
        answerPrompt: allValues.answerPrompt || ''
      };
    };

    // 处理确认操作
    const handleConfirm = async (onlyQuestion = false) => {
      try {
        await form.validateFields();
        
        console.log('Debug - Validation check:', {
          documentId,
          selectedChunkIds,
          selectedChunks,
          selectedChunksLength: selectedChunks.length,
          formRefCurrent: formRef.current,
          questionLlmModel: formRef.current.questionLlmModel,
          answerLlmModel: formRef.current.answerLlmModel,
          documentInfo,
          onlyQuestion
        });
        
        if (!documentId) {
          message.error(t('knowledge.qaPairs.documentNotFound') + 'ID不存在');
          return;
        }
        
        if (!documentInfo) {
          message.error(t('knowledge.qaPairs.fetchDocumentsListFailed'));
          return;
        }
        
        if (selectedChunks.length === 0) {
          message.error('请先选择分块');
          return;
        }
        
        if (!formRef.current.questionLlmModel || formRef.current.questionLlmModel === 0) {
          message.error(t('knowledge.qaPairs.selectQuestionLlmModel'));
          return;
        }

        if (!onlyQuestion && (!formRef.current.answerLlmModel || formRef.current.answerLlmModel === 0)) {
          message.error(t('knowledge.qaPairs.selectAnswerLlmModel'));
          return;
        }

        setConfirmLoading(true);

        // 使用已获取的文档详情和传递过来的chunk数据构建请求参数
        const payload = {
          name: documentInfo.name,
          knowledge_base_id: documentInfo.knowledge_base_id,
          document_id: parseInt(documentId),
          document_source: documentInfo.knowledge_source_type,
          qa_count: formRef.current.qaCount,
          llm_model_id: formRef.current.questionLlmModel,
          answer_llm_model_id: formRef.current.answerLlmModel,
          question_prompt: formRef.current.questionPrompt,
          answer_prompt: formRef.current.answerPrompt,
          only_question: onlyQuestion,
          chunk_list: selectedChunks.map(chunk => ({
            content: chunk.content,
            id: chunk.id
          }))
        };

        console.log('Debug - Request payload:', payload);

        await createQAPairsByChunk(payload);
        message.success(t('knowledge.qaPairs.generateSuccess'));
        
        handleCancel();
        onSuccess?.();
        
      } catch (error) {
        console.error('Generate QA pairs error:', error);
        message.error(t('knowledge.qaPairs.generateFailed'));
      } finally {
        setConfirmLoading(false);
      }
    };

    // 处理取消操作
    const handleCancel = () => {
      setVisible(false);
      setDocumentId('');
      setSelectedChunkIds([]);
      setSelectedChunks([]);
      setDocumentInfo(null);
      form.resetFields();
    };

    return (
      <OperateModal
        title={
          <div className="flex items-center">
            <RobotOutlined className="mr-2 text-blue-500" />
            {t('knowledge.qaPairs.generateTitle')}
          </div>
        }
        open={visible}
        confirmLoading={confirmLoading}
        onCancel={handleCancel}
        cancelText={t('common.cancel')}
        cancelButtonProps={{ disabled: confirmLoading }}
        width={680}
        destroyOnClose
        footer={
          <div className="flex justify-end">
            <Space>
              <Button
                onClick={handleCancel}
                disabled={confirmLoading}
              >
                {t('common.cancel')}
              </Button>
              <Button
                onClick={() => handleConfirm(true)}
                disabled={confirmLoading}
                loading={confirmLoading}
              >
                {t('knowledge.qaPairs.onlyGenerateQuestion')}
              </Button>
              <Button
                type="primary"
                onClick={() => handleConfirm(false)}
                disabled={confirmLoading}
                loading={confirmLoading}
              >
                {t('knowledge.qaPairs.generateQuestionAndAnswer')}
              </Button>
            </Space>
          </div>
        }
      >
        <Spin spinning={loading || llmModelsLoading}>
          <div className="space-y-6">
            <Form
              form={form}
              layout="vertical"
              onValuesChange={handleFormValuesChange}
              initialValues={{
                qaCount: 1,
                questionPrompt: '',
                answerPrompt: ''
              }}
            >
              <Form.Item
                name="questionLlmModel"
                label={
                  <div className="flex items-center">
                    <RobotOutlined className="mr-1" />
                    {t('knowledge.qaPairs.questionLlmModel')}
                  </div>
                }
                rules={[{ required: true, message: t('knowledge.qaPairs.selectQuestionLlmModel') }]}
              >
                <Select
                  placeholder={t('knowledge.qaPairs.selectQuestionLlmModel')}
                  loading={llmModelsLoading}
                  size="large"
                  showSearch
                  optionFilterProp="label"
                  filterOption={(input, option) =>
                    (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                  }
                  options={llmModels.map(model => ({
                    key: model.id,
                    value: model.id,
                    label: model.name,
                    children: (
                      <div className="flex items-center">
                        <RobotOutlined className="mr-2 text-blue-500" />
                        {model.name}
                      </div>
                    )
                  }))}
                />
              </Form.Item>

              <Form.Item
                name="answerLlmModel"
                label={
                  <div className="flex items-center">
                    <RobotOutlined className="mr-1" />
                    {t('knowledge.qaPairs.answerLlmModel')}
                  </div>
                }
                rules={[{ required: true, message: t('knowledge.qaPairs.selectAnswerLlmModel') }]}
              >
                <Select
                  placeholder={t('knowledge.qaPairs.selectAnswerLlmModel')}
                  loading={llmModelsLoading}
                  size="large"
                  showSearch
                  optionFilterProp="label"
                  filterOption={(input, option) =>
                    (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                  }
                  options={llmModels.map(model => ({
                    key: model.id,
                    value: model.id,
                    label: model.name,
                    children: (
                      <div className="flex items-center">
                        <RobotOutlined className="mr-2 text-blue-500" />
                        {model.name}
                      </div>
                    )
                  }))}
                />
              </Form.Item>

              <Form.Item
                name="qaCount"
                label={
                  <div className="flex items-center">
                    <QuestionCircleOutlined className="mr-1" />
                    {t('knowledge.qaPairs.qaCount')}
                  </div>
                }
                rules={[
                  { required: true, message: t('common.required') },
                  { 
                    type: 'number', 
                    min: 1, 
                    max: 1000, 
                    message: t('knowledge.qaPairs.qaCountRange') 
                  }
                ]}
              >
                <InputNumber
                  min={1}
                  max={1000}
                  className="w-full"
                  size="large"
                  placeholder={t('knowledge.qaPairs.enterQaCount')}
                />
              </Form.Item>

              <Form.Item
                name="questionPrompt"
                label={t('knowledge.qaPairs.questionPrompt')}
              >
                <TextArea
                  rows={4}
                  placeholder={t('knowledge.qaPairs.questionPromptPlaceholder')}
                  maxLength={2000}
                  showCount
                />
              </Form.Item>

              <Form.Item
                name="answerPrompt"
                label={t('knowledge.qaPairs.answerPrompt')}
              >
                <TextArea
                  rows={4}
                  placeholder={t('knowledge.qaPairs.answerPromptPlaceholder')}
                  maxLength={2000}
                  showCount
                />
              </Form.Item>
            </Form>

            <div className="flex items-center">
              <Tag color="green" className="flex items-center">
                <span className="mr-1">{t('knowledge.qaPairs.selectedChunks')}:</span>
                <span className="font-semibold">{selectedChunks.length}</span>
              </Tag>
            </div>
          </div>
        </Spin>
      </OperateModal>
    );
  }
);

GenerateQAPairModal.displayName = 'GenerateQAPairModal';

export default GenerateQAPairModal;