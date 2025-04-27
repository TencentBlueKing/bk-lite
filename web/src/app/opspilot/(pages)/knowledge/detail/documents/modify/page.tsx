'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Breadcrumb, Button, Steps, message, Spin } from 'antd';
import LocalFileUpload from './localFileUpload';
import WebLinkForm from './webLinkForm';
import CustomTextForm from './customTextForm';
import PreprocessStep from './preprocessStep';
import ExtractionStep from './extractionStep';
import Icon from '@/components/icon'
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import { 
  getDefaultExtractionMethod,
  getExtractionMethodMap,
  getReverseExtractionMethodMap 
} from '@/app/opspilot/utils/extractionUtils';

const { Step } = Steps;

const KnowledgeModifyPage = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const router = useRouter();
  const type = searchParams ? searchParams.get('type') : null;
  const id = searchParams ? searchParams.get('id') : null;
  const name = searchParams ? searchParams.get('name') : null;
  const desc = searchParams ? searchParams.get('desc') : null;
  const { 
    updateDocumentBaseInfo, 
    createWebPageKnowledge, 
    createFileKnowledge, 
    createManualKnowledge, 
    getDocumentDetail,
    parseContent,
    updateChunkSettings,
    getDocListConfig,
    getDocumentConfig
  } = useKnowledgeApi();

  const [currentStep, setCurrentStep] = useState<number>(0);
  const [isStepValid, setIsStepValid] = useState<boolean>(false);
  const [fileList, setFileList] = useState<File[]>([]);
  const [documentIds, setDocumentIds] = useState<number[]>([]);
  const [extractionConfig, setExtractionConfig] = useState<{
    knowledge_source_type?: string;
    knowledge_document_list?: {
      id: number;
      name?: string;
      enable_ocr_parse: boolean;
      ocr_model: string | null;
      parse_type: string;
    }[];
  } | null>(null);
  const [preprocessConfig, setPreprocessConfig] = useState<any>(null);
  const [webLinkData, setWebLinkData] = useState<{ name: string, link: string, deep: number }>({ name: '', link: '', deep: 1 });
  const [manualData, setManualData] = useState<{ name: string, content: string }>({ name: '', content: '' });
  const [pageLoading, setPageLoading] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(false);
  const [isUpdate, setIsUpdate] = useState<boolean>(false);

  const formRef = useRef<any>(null);

  const sourceTypeToDisplayText: { [key: string]: string } = {
    file: t('knowledge.localFile'),
    web_page: t('knowledge.webLink'),
    manual: t('knowledge.cusText'),
  };


  useEffect(() => {
    const fetchData = async () => {
      const documentIds = searchParams ? searchParams.get('documentIds') : null;

      if (documentIds) {
        setCurrentStep(1);
        setIsUpdate(true);
        setPreprocessConfig({});

        const documentIdArray = documentIds.split(',').map(Number);

        try {
          // Fetch document details
          await fetchDocumentDetails(documentIds);

          // Fetch configuration for a single document if applicable
          if (documentIdArray.length === 1) {
            const config = await getDocumentConfig(documentIdArray[0]);
            setPreprocessConfig(config);
          }
        } catch {
          message.error(t('common.fetchFailed'));
        } finally {
          setPageLoading(false);
        }
      } else {
        setPageLoading(false);
      }
    };

    fetchData();
  }, [searchParams]);

  const fetchDocumentDetails = async (documentIds: string) => {
    try {
      const documentDetails = await getDocListConfig({ doc_ids: documentIds.split(',').map(Number) });
      setDocumentIds(documentIds.split(',').map(Number));
      setExtractionConfig({
        knowledge_source_type: type ?? undefined,
        knowledge_document_list: documentDetails.map((doc: any) => ({
          id: doc.id,
          name: doc.name,
          enable_ocr_parse: doc.enable_ocr_parse,
          ocr_model: doc.ocr_model_id,
          parse_type: getReverseExtractionMethodMap(doc.mode) || 'fullText',
        })),
      });
      setIsStepValid(!!documentIds.length)
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setPageLoading(false);
    }
  };

  const handleSaveKnowledge = async () => {
    try {
      if (type === 'web_page') {
        await formRef.current?.validateFields();
        const params = {
          name: webLinkData.name,
          url: webLinkData.link,
          max_depth: webLinkData.deep,
        };
        if (documentIds.length) {
          await updateDocumentBaseInfo(documentIds[0], params);
        } else {
          const data = await createWebPageKnowledge(id, params);
          setDocumentIds([data]);
        }
        message.success(t('knowledge.documents.webLinkSaveSuccess'));
      } else if (type === 'file') {
        const formData = new FormData();
        formData.append('knowledge_base_id', id as string);
        fileList.forEach(file => formData.append('files', file));
        const data = await createFileKnowledge(formData);
        setDocumentIds(data);
        message.success(t('knowledge.documents.fileUploadSuccess'));
      } else if (type === 'manual') {
        const params = {
          name: manualData.name,
          content: manualData.content,
        };
        if (documentIds.length) {
          await updateDocumentBaseInfo(documentIds[0], params);
        } else {
          const data = await createManualKnowledge(id, params);
          setDocumentIds([data]);
        }
        message.success(t('knowledge.documents.manualDataSaveSuccess'));
      }
    } catch (error) {
      if (type === 'web_page') {
        message.error(t('knowledge.documents.webLinkSaveFail'));
      } else if (type === 'file') {
        message.error(t('knowledge.documents.fileUploadFailed'));
      } else if (type === 'manual') {
        message.error(t('knowledge.documents.manualDataSaveFailed'));
      }
      setLoading(false);
      throw error;
    }
  };

  const buildExtractionConfig = () => {
    const baseConfig = {
      knowledge_source_type: type || 'file',
      knowledge_document_list: extractionConfig?.knowledge_document_list || [],
    };

    if (type === 'file') {
      if (!isUpdate) {
        baseConfig.knowledge_document_list = fileList.map((file, index) => {
          const extension = file.name.split('.').pop()?.toLowerCase() || 'text';
          const existingConfig = extractionConfig?.knowledge_document_list?.find((doc) => doc.id === documentIds[index]);
          return {
            id: documentIds[index] || index,
            enable_ocr_parse: existingConfig?.enable_ocr_parse ?? false,
            ocr_model: existingConfig?.ocr_model ?? null,
            parse_type: existingConfig?.parse_type ?? getDefaultExtractionMethod(extension),
          };
        });
      }
    } else if (type === 'web_page' || type === 'manual') {
      baseConfig.knowledge_document_list = documentIds.map((docId, index) => ({
        id: docId || index,
        enable_ocr_parse: extractionConfig?.knowledge_document_list?.[index]?.enable_ocr_parse ?? false,
        ocr_model: extractionConfig?.knowledge_document_list?.[index]?.ocr_model ?? null,
        parse_type: extractionConfig?.knowledge_document_list?.[index]?.parse_type ?? 'fullText',
      }));
    }

    // Ensure the correct property name (`mode`) is used when sending to the backend
    baseConfig.knowledge_document_list = baseConfig.knowledge_document_list.map((doc) => ({
      ...doc,
      mode: getExtractionMethodMap(doc.parse_type),
    }));

    return baseConfig;
  };

  const handleNext = async () => {
    setLoading(true);

    try {
      if (currentStep === 0) {
        await handleSaveKnowledge();
      } else if (currentStep === 1) {
        const updatedConfig = buildExtractionConfig();
        await parseContent(updatedConfig);
        message.success(t('common.saveSuccess'));
        if (!preprocessConfig) {
          const defaultConfig = {
            knowledge_source_type: type || 'file',
            knowledge_document_list: documentIds,
            general_parse_chunk_size: 256,
            general_parse_chunk_overlap: 0,
            semantic_chunk_parse_embedding_model: null,
            chunk_type: 'fixed_size',
          };
          setPreprocessConfig(defaultConfig);
        }
      } else if (currentStep === 2) {
        await updateChunkSettings(preprocessConfig);
        message.success(t('common.saveSuccess'));
      }
      setCurrentStep(currentStep + 1);
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handlePrevious = async () => {
    if (isUpdate && (type === 'web_page' || type === 'manual')) {
      const data = await getDocumentDetail(documentIds[0]);
      if (type === 'web_page') {
        setWebLinkData({
          name: data.name,
          link: data.url,
          deep: data.max_depth,
        });
        setIsStepValid(data.name.trim() !== '' && data.url.trim() !== '');
      } else if (type === 'manual') {
        setManualData({
          name: data.name,
          content: data.content,
        });
        setIsStepValid(data.name.trim() !== '' && data.content.trim() !== '');
      }
    } else if (currentStep === 2) {
      setIsStepValid(preprocessConfig !== null);
    } else if (currentStep === 1) {
      setIsStepValid(fileList.length > 0 || !!extractionConfig);
    }
    setCurrentStep(currentStep - 1);
  };

  const handleValidationChange = useCallback((isValid: boolean) => {
    setIsStepValid(isValid);
  }, []);

  const handleFileChange = useCallback((files: File[]) => {
    setFileList(files);
    setIsStepValid(files.length > 0);
  }, []);

  const handlePreprocessConfigChange = useCallback((config: any) => {
    setPreprocessConfig(config);
    setIsStepValid(true);
  }, []);

  const handleExtractionConfigChange = useCallback((config: any) => {
    setExtractionConfig(config);
    setIsStepValid(true);
  }, []);

  const handleWebLinkDataChange = useCallback((data: { name: string, link: string, deep: number }) => {
    setWebLinkData(data);
  }, []);

  const handleManualDataChange = useCallback((data: { name: string, content: string }) => {
    setManualData(data);
  }, []);

  const handleDone = () => {
    router.push(`/opspilot/knowledge/detail/documents?id=${id}&name=${name}&desc=${desc}&type=${type}`);
  };

  const handleToTesting = () => {
    router.push(`/opspilot/knowledge/detail/testing?id=${id}&name=${name}&desc=${desc}`);
  };

  const renderStepContent = () => {
    switch (type) {
      case 'file':
        return <LocalFileUpload onFileChange={handleFileChange} initialFileList={fileList} />;
      case 'web_page':
        return <WebLinkForm ref={formRef} initialData={webLinkData} onFormChange={handleValidationChange} onFormDataChange={handleWebLinkDataChange} />;
      case 'manual':
        return <CustomTextForm initialData={manualData} onFormChange={handleValidationChange} onFormDataChange={handleManualDataChange} />;
      default:
        return <LocalFileUpload onFileChange={handleFileChange} initialFileList={fileList} />;
    }
  };

  const steps = [
    {
      title: t('knowledge.choose'),
      content: renderStepContent(),
    },
    {
      title: t('knowledge.extract'),
      content: <ExtractionStep
        knowledgeDocumentIds={documentIds}
        fileList={fileList}
        type={type}
        webLinkData={type === 'web_page' ? webLinkData : null}
        manualData={type === 'manual' ? manualData : null}
        extractionConfig={extractionConfig || undefined}
        onConfigChange={handleExtractionConfigChange}
      />,
    },
    {
      title: t('knowledge.preprocess'),
      content: <PreprocessStep
        knowledgeSourceType={type}
        knowledgeDocumentIds={documentIds}
        onConfigChange={handlePreprocessConfigChange}
        initialConfig={preprocessConfig || {}}
      />,
    },
    {
      title: t('knowledge.finish'),
      content: (
        <div className="flex flex-col items-center">
          <Icon className="text-8xl mb-2" type="finish" />
          <p>{t('knowledge.finishTip')}</p>
          <p>
            <span className='text-blue-500 cursor-pointer' onClick={handleDone}>{t('knowledge.backToList')}</span>
            <span> {t('knowledge.or')} </span>
            <span className='text-blue-500 cursor-pointer' onClick={handleToTesting}>{t('knowledge.goToTesting')}</span>
          </p>
        </div>
      ),
    },
  ];

  return (
    <div>
      <Breadcrumb>
        <Breadcrumb.Item>{t('knowledge.menu')}</Breadcrumb.Item>
        <Breadcrumb.Item>{type && sourceTypeToDisplayText[type]}</Breadcrumb.Item>
        <Breadcrumb.Item>{isUpdate ? t('common.update') : t('common.create')}</Breadcrumb.Item>
      </Breadcrumb>
      <div className="px-7 py-5">
        {pageLoading ? (
          <div className="flex items-center justify-center h-full">
            <Spin />
          </div>
        ) : (
          <div>
            <Steps className="py-8" current={currentStep}>
              {steps.map((step, index) => (
                <Step key={index} title={step.title} />
              ))}
            </Steps>
            <div className="steps-content" style={{ height: 'calc(100vh - 380px', overflowY: 'auto' }}>
              {steps[currentStep].content}
            </div>
          </div>
        )}
        <div className="fixed bottom-10 right-10 z-50 flex space-x-2">
          {currentStep > 0 && currentStep < steps.length - 1 && (
            <Button onClick={handlePrevious} disabled={isUpdate && currentStep === 1}>
              {t('common.pre')}
            </Button>
          )}
          {currentStep < steps.length - 1 && (
            <Button type="primary" onClick={handleNext} disabled={!isStepValid} loading={loading}>
              {currentStep === 2 ? t('knowledge.finish') : t('common.next')}
            </Button>
          )}
          {currentStep === steps.length - 1 && (
            <Button type="primary" onClick={handleDone}>
              {t('common.done')}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default KnowledgeModifyPage;
