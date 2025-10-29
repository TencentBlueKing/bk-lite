import React, { useState, useEffect, forwardRef, useImperativeHandle, useCallback, useMemo, useRef } from 'react';
import { Form, Select, InputNumber, Tabs, message, Button, Drawer, Space, Tag, Divider, Empty, Input, Card, Spin, Skeleton } from 'antd';
import { PlusOutlined, CloseOutlined, ClearOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import { useSkillApi } from '@/app/opspilot/api/skill';
import { useSearchParams } from 'next/navigation';
import CustomTable from '@/components/custom-table';
import Icon from '@/components/icon';
import type { DocumentItem, QAPairFormProps, PreviewQAPair } from '@/app/opspilot/types/knowledge';

const { TabPane } = Tabs;
const { TextArea } = Input;

const QAPairForm = forwardRef<any, QAPairFormProps>(({ 
  initialData, 
  onFormChange = () => {}, 
  onFormDataChange = () => {} 
}, ref) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;
  const parId = searchParams ? searchParams.get('parId') : null;
  const { 
    fetchDocuments, 
    createQAPairs, 
    generateQuestions, 
    generateAnswers,
    getQAPairDetail,
    updateQAPairConfig 
  } = useKnowledgeApi();
  const { fetchLlmModels: fetchLlmModelsApi } = useSkillApi();

  const [llmModels, setLlmModels] = useState<any[]>([]);
  const [llmModelsLoading, setLlmModelsLoading] = useState<boolean>(false);
  const [documentData, setDocumentData] = useState<{[key: string]: DocumentItem[]}>({
    file: [],
    web_page: [],
    manual: []
  });
  const [documentTotalCounts, setDocumentTotalCounts] = useState<{[key: string]: number}>({
    file: 0,
    web_page: 0,
    manual: 0
  });
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([]);
  const [activeDocumentTab, setActiveDocumentTab] = useState<string>('file');
  const [loading, setLoading] = useState<boolean>(false);
  const [drawerVisible, setDrawerVisible] = useState<boolean>(false);
  const [tempSelectedDocuments, setTempSelectedDocuments] = useState<string[]>([]);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  
  const [previewQAPairs, setPreviewQAPairs] = useState<PreviewQAPair[]>([]);
  const [questionGenerating, setQuestionGenerating] = useState<boolean>(false);
  const [answerGenerating, setAnswerGenerating] = useState<boolean>(false);
  const [questionsGenerated, setQuestionsGenerated] = useState<boolean>(false);
  const [isEditMode, setIsEditMode] = useState<boolean>(false);
  
  const formValuesRef = useRef({
    questionLlmModel: 0,
    answerLlmModel: 0,
    qaCount: 1,
    questionPrompt: '',
    answerPrompt: ''
  });
  const onFormChangeRef = useRef(onFormChange);
  const onFormDataChangeRef = useRef(onFormDataChange);

  // 添加表单准备状态
  const [formReady, setFormReady] = useState(false);
  const [editData, setEditData] = useState<any>(null);

  useEffect(() => {
    onFormChangeRef.current = onFormChange;
    onFormDataChangeRef.current = onFormDataChange;
  }, [onFormChange, onFormDataChange]);

  useImperativeHandle(ref, () => ({
    validateFields: () => form.validateFields(),
    getFieldsValue: () => ({
      ...formValuesRef.current,
      selectedDocuments
    }),
    createQAPairs: handleCreateQAPairs
  }));

  const validateAndNotify = useCallback(() => {
    const hasValidDocuments = isEditMode || selectedDocuments.length > 0;
    const isValid = !!(
      (formValuesRef.current.questionLlmModel !== undefined && formValuesRef.current.questionLlmModel !== null) && 
      (formValuesRef.current.answerLlmModel !== undefined && formValuesRef.current.answerLlmModel !== null) && 
      formValuesRef.current.qaCount && 
      formValuesRef.current.qaCount > 0 &&
      hasValidDocuments
    );
    
    onFormChangeRef.current(isValid);
    onFormDataChangeRef.current({
      ...formValuesRef.current,
      selectedDocuments
    });
  }, [selectedDocuments, isEditMode]);

  const fetchLlmModels = useCallback(async () => {
    setLlmModelsLoading(true);
    try {
      const models = await fetchLlmModelsApi();
      setLlmModels(models);
      
      if (!parId && !initialData?.questionLlmModel && models.length > 0) {
        const defaultValues = {
          questionLlmModel: models[0].id,
          answerLlmModel: models[0].id,
          qaCount: 1,
          questionPrompt: '请根据我提供的文本内容，生成与其紧密相关的问题，要求如下：\n1、仔细阅读并理解整段文本（该文本为长文档的一个分块）。\n2、从文本中提炼3-5个关键信息点，并据此生成问题。\n3、问题应涵盖主要事实、细节、原因、影响等，不要集中在单一方面。\n4、问题必须基于原文内容，不能引入不存在或推测性的信息。\n5、问题应简洁、明确、完整，不带有"根据本文"或"文中提到"等表述。\n6、仅输出问题列表，每行一个，不附加答案。',
          answerPrompt: '请根据我提供的文本和相应问题列表，生成每个问题的答案，要求如下：\n1、仔细阅读文本，逐一回答问题。\n2、答案必须严格基于源文信息，不能编造或添加未提及内容。\n3、保持客观中立，避免主观评价或情感化表达。\n4、每个答案应完整且清晰。'
        };
        form.setFieldsValue(defaultValues);
        formValuesRef.current = defaultValues;
        
        // 设置默认值后立即触发验证
        setTimeout(() => {
          validateAndNotify();
        }, 100);
      }
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLlmModelsLoading(false);
    }
  }, [parId, initialData, validateAndNotify]);

  const fetchDocumentsByType = useCallback(async (type: string, page: number, pageSize: number) => {
    if (!id) return;
    
    setLoading(true);
    try {
      const result = await fetchDocuments({
        knowledge_source_type: type,
        knowledge_base_id: id ? parseInt(id, 10) : undefined,
        page,
        page_size: pageSize
      });

      const processedItems = result.items.map((item: any) => ({
        key: item.id.toString(),
        title: item.name,
        chunk_size: item.chunk_size || 0,
      }));
      
      setDocumentData(prev => ({
        ...prev,
        [type]: processedItems
      }));
      
      setDocumentTotalCounts(prev => ({
        ...prev,
        [type]: result.count || result.items.length
      }));
      
    } catch {
      message.error(t('knowledge.qaPairs.fetchDocumentsListFailed'));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (drawerVisible && activeDocumentTab && id) {
      fetchDocumentsByType(activeDocumentTab, currentPage, pageSize);
    }
  }, [drawerVisible, activeDocumentTab, currentPage, pageSize, id]);

  useEffect(() => {
    fetchLlmModels();
  }, []);

  // 监听表单准备状态
  useEffect(() => {
    if (!llmModelsLoading && llmModels.length > 0) {
      setFormReady(true);
    }
  }, [llmModelsLoading, llmModels]);

  useEffect(() => {
    if (initialData) {
      const values = {
        questionLlmModel: initialData.questionLlmModel || 0,
        answerLlmModel: initialData.answerLlmModel || 0,
        qaCount: initialData.qaCount || 1,
        questionPrompt: initialData.questionPrompt || '',
        answerPrompt: initialData.answerPrompt || ''
      };
      form.setFieldsValue(values);
      formValuesRef.current = values;
      
      if (!isEditMode && initialData.selectedDocuments) {
        setSelectedDocuments(initialData.selectedDocuments);
      }
    }
  }, [initialData, form, isEditMode]);

  // 获取编辑数据
  useEffect(() => {
    const fetchQAPairDetails = async () => {
      if (!parId) return;
      
      setIsEditMode(true);
      try {
        const qaPairDetail = await getQAPairDetail(Number(parId));
        
        const editValues = {
          questionLlmModel: qaPairDetail.llm_model,
          answerLlmModel: qaPairDetail.answer_llm_model,
          qaCount: qaPairDetail.qa_count,
          questionPrompt: qaPairDetail.question_prompt || '',
          answerPrompt: qaPairDetail.answer_prompt || ''
        };
        
        if (qaPairDetail.document_id) {
          const documentKeys = [qaPairDetail.document_id.toString()];
          setSelectedDocuments(documentKeys);
        }
        
        // 保存编辑数据，等待表单准备好后再设置
        setEditData(editValues);
        
      } catch (error) {
        console.error('Failed to fetch QA pair details:', error);
        message.error(t('common.fetchFailed'));
      }
    };

    fetchQAPairDetails();
  }, [parId]);

  // 当表单准备好且有编辑数据时，设置表单值
  useEffect(() => {
    if (formReady && editData && parId) {
      // 使用 setTimeout 确保表单完全渲染
      setTimeout(() => {
        try {
          form.setFieldsValue(editData);
          formValuesRef.current = editData;
          
          // 立即触发验证
          validateAndNotify();
          
        } catch (error) {
          console.error('设置表单值时出错:', error);
        }
      }, 200);
    }
  }, [formReady, editData, parId, form]);

  useEffect(() => {
    if (parId) {
      setIsEditMode(true);
    } else {
      setIsEditMode(false);
    }
  }, [parId]);
  
  const handleDocumentSelect = useCallback((keys: React.Key[]) => {
    setTempSelectedDocuments(keys.map(key => key.toString()));
  }, []);

  const handleTempRemoveDocument = useCallback((documentKey: string) => {
    setTempSelectedDocuments(prev => prev.filter(key => key !== documentKey));
  }, []);

  const handleTempClearAllDocuments = useCallback(() => {
    setTempSelectedDocuments([]);
  }, []);

  const getSelectedDocumentInfo = useCallback((documentKey: string) => {
    for (const type in documentData) {
      const doc = documentData[type].find(item => item.key === documentKey);
      if (doc) {
        return { ...doc, type };
      }
    }
    return null;
  }, [documentData]);

  const tempSelectedDocumentsList = useMemo(() => {
    return tempSelectedDocuments.map(key => {
      const docInfo = getSelectedDocumentInfo(key);
      return docInfo ? { ...docInfo } : { key, title: t('knowledge.qaPairs.defaultDocumentTitle') + key, type: 'unknown' };
    }).filter(Boolean);
  }, [tempSelectedDocuments, getSelectedDocumentInfo, t]);

  const getDocumentTypeLabel = useCallback((type: string) => {
    switch (type) {
      case 'file':
        return t('knowledge.localFile');
      case 'web_page':
        return t('knowledge.webLink');
      case 'manual':
        return t('knowledge.cusText');
      default:
        return type;
    }
  }, []);

  const handleFormValuesChange = useCallback((_: any, allValues: any) => {
    const newValues = {
      questionLlmModel: allValues.questionLlmModel !== undefined ? allValues.questionLlmModel : 0,
      answerLlmModel: allValues.answerLlmModel !== undefined ? allValues.answerLlmModel : 0,
      qaCount: allValues.qaCount || 1,
      questionPrompt: allValues.questionPrompt || '',
      answerPrompt: allValues.answerPrompt || ''
    };
    formValuesRef.current = newValues;
    
    // 立即触发验证，不使用异步
    const hasValidDocuments = isEditMode || selectedDocuments.length > 0;
    const isValid = !!(
      (newValues.questionLlmModel !== undefined && newValues.questionLlmModel !== null) && 
      (newValues.answerLlmModel !== undefined && newValues.answerLlmModel !== null) && 
      newValues.qaCount && 
      newValues.qaCount > 0 &&
      hasValidDocuments
    );
    
    onFormChangeRef.current(isValid);
    onFormDataChangeRef.current({
      ...newValues,
      selectedDocuments
    });
  }, [selectedDocuments, isEditMode]);

  useEffect(() => {
    const cleanup = validateAndNotify();
    return cleanup;
  }, []);

  // 监听 selectedDocuments 变化，触发验证
  useEffect(() => {
    validateAndNotify();
  }, [selectedDocuments, validateAndNotify]);

  const handleTabChange = useCallback((tabKey: string) => {
    setActiveDocumentTab(tabKey);
    setCurrentPage(1);
  }, []);

  const handlePaginationChange = useCallback((page: number, size: number) => {
    setCurrentPage(page);
    if (size !== pageSize) {
      setPageSize(size);
      setCurrentPage(1);
    }
  }, [pageSize]);

  const paginatedDocuments = useMemo(() => {
    return documentData[activeDocumentTab] || [];
  }, [documentData, activeDocumentTab]);

  const columns = useMemo(() => [
    {
      title: t('knowledge.documents.name'),
      dataIndex: 'title',
      key: 'title',
      render: (text: string) => (
        <div className="font-medium">{text}</div>
      ),
    },
    {
      title: t('knowledge.documents.chunkSize'),
      dataIndex: 'chunk_size',
      key: 'chunk_size',
      width: 120,
      render: (size: number) => (
        <Tag color="blue" className="text-xs">
          {size || 0}
        </Tag>
      ),
    }
  ], []);

  const handleCreateQAPairs = useCallback(async (onlyQuestion = false) => {
    if (!id || !formValuesRef.current.questionLlmModel || !formValuesRef.current.answerLlmModel) {
      message.error(t('knowledge.qaPairs.ensureDocumentsAndModelsSelected'));
      return;
    }

    if (!isEditMode && selectedDocuments.length === 0) {
      message.error(t('knowledge.qaPairs.ensureDocumentsAndModelsSelected'));
      return;
    }

    try {
      await form.validateFields();
      
      setLoading(true);
      
      if (isEditMode && parId) {
        const updatePayload = {
          llm_model_id: formValuesRef.current.questionLlmModel,
          qa_count: formValuesRef.current.qaCount,
          question_prompt: formValuesRef.current.questionPrompt,
          answer_prompt: formValuesRef.current.answerPrompt,
          answer_llm_model_id: formValuesRef.current.answerLlmModel,
          only_question: onlyQuestion
        };

        await updateQAPairConfig(Number(parId), updatePayload);
        message.success(t('knowledge.qaPairs.qaPairsUpdateSuccess'));
      } else {
        const documentList = selectedDocuments.map(docKey => {
          const docInfo = getSelectedDocumentInfo(docKey);
          return {
            name: docInfo?.title || t('knowledge.qaPairs.documentPrefix') + docKey,
            document_id: parseInt(docKey),
            document_source: docInfo?.type || 'file'
          };
        });

        const payload = {
          knowledge_base_id: parseInt(id),
          llm_model_id: formValuesRef.current.questionLlmModel,
          answer_llm_model_id: formValuesRef.current.answerLlmModel,
          qa_count: formValuesRef.current.qaCount,
          question_prompt: formValuesRef.current.questionPrompt,
          answer_prompt: formValuesRef.current.answerPrompt,
          document_list: documentList,
          only_question: onlyQuestion
        };

        await createQAPairs(payload);
        message.success(t('knowledge.qaPairs.qaPairsCreateSuccess'));
      }
      
      return Promise.resolve();
      
    } catch (error) {
      message.error(isEditMode ? t('knowledge.qaPairs.qaPairsUpdateFailed') : t('knowledge.qaPairs.qaPairsCreateFailed'));
      throw error;
    } finally {
      setLoading(false);
    }
  }, [id, selectedDocuments, form, isEditMode, parId]);

  const handleGenerateQuestions = useCallback(async () => {
    if (!id || selectedDocuments.length === 0 || !formValuesRef.current.questionLlmModel) {
      message.error(t('knowledge.qaPairs.ensureDocumentsAndModelsSelected'));
      return;
    }

    setQuestionGenerating(true);
    try {
      const previewDocuments = selectedDocuments.slice(0, 10);
      
      const payload = {
        document_list: previewDocuments.map(docKey => ({ document_id: parseInt(docKey) })),
        knowledge_base_id: parseInt(id),
        llm_model_id: formValuesRef.current.questionLlmModel,
        question_prompt: formValuesRef.current.questionPrompt || form.getFieldValue('questionPrompt') || ''
      };

      const questionData = await generateQuestions(payload);
      
      setPreviewQAPairs(questionData.map(item => ({
        question: item.question,
        content: item.content
      })));
      setQuestionsGenerated(true);
      message.success(t('knowledge.qaPairs.questionGenerateSuccess'));
    } catch (error) {
      message.error(t('knowledge.qaPairs.questionGenerateFailed'));
      console.error('Generate questions error:', error);
    } finally {
      setQuestionGenerating(false);
    }
  }, [id, selectedDocuments, form]);

  const handleGenerateAnswers = useCallback(async () => {
    if (!formValuesRef.current.answerLlmModel || previewQAPairs.length === 0) {
      message.error(t('knowledge.qaPairs.generateQuestionFirst'));
      return;
    }

    setAnswerGenerating(true);
    try {
      const payload = {
        answer_llm_model_id: formValuesRef.current.answerLlmModel,
        answer_prompt: formValuesRef.current.answerPrompt || form.getFieldValue('answerPrompt') || '',
        knowledge_base_id: id ? parseInt(id, 10) : 0,
        question_data: previewQAPairs.map(item => ({
          question: item.question,
          content: item.content
        }))
      };

      const answerData = await generateAnswers(payload);
      
      setPreviewQAPairs(prev => prev.map((item, index) => ({
        ...item,
        answer: answerData[index]?.answer || ''
      })));
      message.success(t('knowledge.qaPairs.answerGenerateSuccess'));
    } catch (error) {
      message.error(t('knowledge.qaPairs.answerGenerateFailed'));
      console.error('Generate answers error:', error);
    } finally {
      setAnswerGenerating(false);
    }
  }, [previewQAPairs, form]);

  return (
    <div className="flex gap-6 h-full">
      <div className="w-1/2 flex flex-col">
        {llmModelsLoading ? (
          <div className="space-y-4">
            <Skeleton active paragraph={{ rows: 1 }} />
            <Skeleton active paragraph={{ rows: 1 }} />
            <Skeleton active paragraph={{ rows: 1 }} />
            <Skeleton active paragraph={{ rows: 1 }} />
            <Skeleton active paragraph={{ rows: 3 }} />
            <Skeleton active paragraph={{ rows: 3 }} />
          </div>
        ) : (
          <Form
            form={form}
            layout="vertical"
            initialValues={{ qaCount: 1, ...initialData }}
            onValuesChange={handleFormValuesChange}
            className="flex-1"
          >
            <Form.Item
              name="questionLlmModel"
              label={t('knowledge.qaPairs.questionLlmModel')}
              rules={[{ required: true, message: t('knowledge.qaPairs.selectQuestionLlmModel') }]}
            >
              <Select
                placeholder={t('knowledge.qaPairs.selectQuestionLlmModel')}
                loading={llmModelsLoading}
                showSearch
                filterOption={(input, option) =>
                  typeof option?.children === 'string' && (option.children as string).toLowerCase().includes(input.toLowerCase())
                }
              >
                {llmModels.map(model => (
                  <Select.Option key={model.id} value={model.id}>
                    {model.name}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>

            <Form.Item
              name="answerLlmModel"
              label={t('knowledge.qaPairs.answerLlmModel')}
              rules={[{ required: true, message: t('knowledge.qaPairs.selectAnswerLlmModel') }]}
            >
              <Select
                placeholder={t('knowledge.qaPairs.selectAnswerLlmModel')}
                loading={llmModelsLoading}
                showSearch
                filterOption={(input, option) =>
                  typeof option?.children === 'string' && (option.children as string).toLowerCase().includes(input.toLowerCase())
                }
              >
                {llmModels.map(model => (
                  <Select.Option key={model.id} value={model.id}>
                    {model.name}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>

            <Form.Item
              name="qaCount"
              label={t('knowledge.qaPairs.qaCount')}
              rules={[{ required: true }]}
            >
              <InputNumber
                min={1}
                max={1000}
                className="w-full"
              />
            </Form.Item>

            <Form.Item
              label={t('knowledge.qaPairs.targetDocuments')}
              required={!isEditMode}
            >
              <div>
                {!isEditMode && (
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    size="small"
                    onClick={() => {
                      setTempSelectedDocuments(selectedDocuments);
                      setDrawerVisible(true);
                    }}
                  >
                    {t('common.add')}
                  </Button>
                )}
                <span className="text-blue-500 ml-2">
                  {isEditMode ? (
                    selectedDocuments.length > 0 ? 
                      `(${selectedDocuments.length}) ${t('knowledge.qaPairs.documentsSelected')}` :
                      `(${selectedDocuments.length}) ${t('knowledge.qaPairs.noDocumentsSelected')}`
                  ) : (
                    `(${selectedDocuments.length}) ${t('knowledge.qaPairs.documentsSelected')}`
                  )}
                </span>
              </div>
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
        )}
      </div>

      <div className="w-1/2 flex flex-col">
        <div className="flex-1 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-medium m-0">{t('knowledge.qaPairs.preview')}</h3>
            <Space>
              <Button
                type="primary"
                onClick={handleGenerateQuestions}
                loading={questionGenerating}
                disabled={selectedDocuments.length === 0 || !formValuesRef.current.questionLlmModel}
              >
                {t('knowledge.qaPairs.generateQuestion')}
              </Button>
              <Button
                type="primary"
                onClick={handleGenerateAnswers}
                loading={answerGenerating}
                disabled={!questionsGenerated || previewQAPairs.length === 0 || !formValuesRef.current.answerLlmModel}
              >
                {t('knowledge.qaPairs.generateAnswer')}
              </Button>
            </Space>
          </div>
          
          <div className="flex-1 overflow-auto">
            {questionGenerating || answerGenerating ? (
              <div className="flex justify-center items-center h-32">
                <Spin size="large" />
              </div>
            ) : previewQAPairs.length === 0 ? (
              <Empty
                description={t('knowledge.qaPairs.previewDescription')}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {previewQAPairs.map((qaPair, index) => (
                  <Card
                    key={index}
                    size="small"
                    className="min-h-[120px] bg-[var(--color-fill-2)]"
                  >
                    <div className="flex flex-col h-full">
                      <div className="flex-1 flex flex-col mb-3">
                        <div className="flex items-start gap-2">
                          <Icon type="question-circle-fill" className="mt-1 flex-shrink-0 text-blue-500" />
                          <p className="line-clamp-2 text-ellipsis overflow-hidden leading-6 m-0 text-xs text-[var(--color-text-1)] font-medium">
                            {qaPair.question || '--'}
                          </p>
                        </div>
                      </div>
                      {qaPair.answer && (
                        <>
                          <Divider className="my-2" />
                          <div className="flex-1 flex flex-col">
                            <div className="flex items-start gap-2">
                              <Icon type="answer" className="mt-1 flex-shrink-0 text-green-500" />
                              <p className="line-clamp-2 text-ellipsis overflow-hidden leading-6 m-0 text-xs text-[var(--color-text-3)]">
                                {qaPair.answer || '--'}
                              </p>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <Drawer
        title={t('knowledge.qaPairs.selectDocuments')}
        placement="right"
        width={900}
        onClose={() => setDrawerVisible(false)}
        open={drawerVisible}
        footer={
          <div className="flex justify-end space-x-2">
            <Button onClick={() => setDrawerVisible(false)}>
              {t('common.cancel')}
            </Button>
            <Button 
              type="primary" 
              onClick={() => {
                setSelectedDocuments(tempSelectedDocuments);
                setDrawerVisible(false);
                message.success(t('knowledge.qaPairs.documentsSelectedSuccess') + `：${tempSelectedDocuments.length}`);
              }}
            >
              {t('common.confirm')} ({tempSelectedDocuments.length})
            </Button>
          </div>
        }
      >
        <div className="flex gap-4" style={{ height: 'calc(100vh - 160px)' }}>
          <div className="w-3/5 border rounded-lg p-4 flex flex-col">
            <Tabs
              activeKey={activeDocumentTab}
              onChange={handleTabChange}
              size="small"
            >
              <TabPane tab={t('knowledge.localFile')} key="file" />
              <TabPane tab={t('knowledge.webLink')} key="web_page" />
              <TabPane tab={t('knowledge.cusText')} key="manual" />
            </Tabs>
            
            <div className="flex-1 mt-4">
              <CustomTable
                size="small"
                columns={columns}
                dataSource={paginatedDocuments}
                rowSelection={{
                  type: 'checkbox',
                  selectedRowKeys: tempSelectedDocuments,
                  onChange: handleDocumentSelect,
                  preserveSelectedRowKeys: true,
                }}
                pagination={{
                  current: currentPage,
                  total: documentTotalCounts[activeDocumentTab],
                  pageSize: pageSize,
                  showSizeChanger: true,
                  onChange: handlePaginationChange,
                }}
                loading={loading}
                scroll={{ 
                  y: 'calc(100vh - 370px)',
                }}
              />
            </div>
          </div>

          <div className="w-2/5 flex flex-col">
            <div className="border rounded-lg p-4 h-full flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-base font-medium m-0">
                  {t('knowledge.qaPairs.pendingDocuments')} ({tempSelectedDocuments.length})
                </h4>
                {tempSelectedDocuments.length > 0 && (
                  <Button
                    type="text"
                    size="small"
                    icon={<ClearOutlined />}
                    onClick={handleTempClearAllDocuments}
                    className="text-red-500 hover:text-red-700"
                  >
                    {t('common.clear')}
                  </Button>
                )}
              </div>
              
              <Divider className="my-2" />
              
              <div className="flex-1 overflow-auto">
                {tempSelectedDocumentsList.length === 0 ? (
                  <Empty 
                    description={t('knowledge.qaPairs.selectFromLeftTable')}
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    className="mt-8"
                  />
                ) : (
                  <div className="space-y-2">
                    {tempSelectedDocumentsList.map(doc => (
                      <div
                        key={doc.key}
                        className="flex items-start justify-between p-3 bg-blue-50 rounded-md hover:bg-blue-100 transition-colors border border-blue-200"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <Tag 
                              color="blue"
                              className="text-xs"
                            >
                              {getDocumentTypeLabel(doc.type)}
                            </Tag>
                          </div>
                          <div 
                            className="text-sm font-medium text-gray-900 truncate"
                            title={doc.title}
                          >
                            {doc.title}
                          </div>
                        </div>
                        <Button
                          type="text"
                          size="small"
                          icon={<CloseOutlined />}
                          onClick={() => handleTempRemoveDocument(doc.key)}
                          className="text-gray-400 hover:text-red-500 flex-shrink-0 ml-2"
                          style={{ minWidth: 'auto', padding: '4px' }}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
              
              {tempSelectedDocuments.length > 0 && (
                <div className="mt-4 pt-3 border-t border-gray-200 flex-shrink-0">
                  <div className="text-xs text-blue-600 text-center">
                    {t('knowledge.qaPairs.clickConfirmToApply')}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </Drawer>
    </div>
  );
});

QAPairForm.displayName = 'QAPairForm';

export default QAPairForm;