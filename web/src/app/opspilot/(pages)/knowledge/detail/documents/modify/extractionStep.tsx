import React, { useState, useEffect, useMemo } from 'react';
import { Button, Select, Switch, Form, message, Image, Alert } from 'antd';
import { WarningOutlined } from '@ant-design/icons';
import Link from 'next/link';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import styles from './modify.module.scss';
import { ModelOption } from '@/app/opspilot/types/knowledge';
import fullTextImg from '@/app/opspilot/img/full_text_extraction.png';
import chapterImg from '@/app/opspilot/img/chapter_extraction.png';
import worksheetImg from '@/app/opspilot/img/worksheet_extraction.png';
import rowImg from '@/app/opspilot/img/row_level_extraction.png';

const { Option } = Select;

const ExtractionStep: React.FC<{
  knowledgeDocumentIds: number[];
  fileList: File[];
  type: string | null;
  webLinkData?: { name: string; link: string; deep: number } | null;
  manualData?: { name: string; content: string } | null;
  onConfigChange?: (config: any) => void;
  extractionConfig?: {
    knowledge_source_type?: string;
    knowledge_document_list?: {
      id: number;
      name?: string;
      enable_ocr_parse: boolean;
      ocr_model: string | null;
      parse_type: string;
    }[];
  };
}> = ({ knowledgeDocumentIds, fileList, type, webLinkData, manualData, onConfigChange, extractionConfig }) => {
  const { t } = useTranslation();
  const { fetchOcrModels } = useKnowledgeApi();
  const [modalVisible, setModalVisible] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<any>(null);
  const [selectedMethod, setSelectedMethod] = useState<keyof typeof extractionMethods | null>(null);
  const [ocrEnabled, setOcrEnabled] = useState<boolean>(false);
  const [ocrModels, setOcrModels] = useState<ModelOption[]>([]);
  const [loadingOcrModels, setLoadingOcrModels] = useState<boolean>(true);
  const [selectedOcrModel, setSelectedOcrModel] = useState<string | null>(null);

  const allOcrModelsDisabled = useMemo(() => {
    return ocrModels.length > 0 && ocrModels.every((model) => !model.enabled);
  }, [ocrModels]);

  // Extraction methods configuration
  const extractionMethods = {
    fullText: {
      label: t('knowledge.documents.fullTextExtraction'),
      description: {
        formats: t('knowledge.documents.fullTextFormats'),
        method: t('knowledge.documents.fullTextMethod'),
        description: t('knowledge.documents.fullTextDescription'),
      },
      defaultOCR: false,
      img: fullTextImg,
    },
    chapter: {
      label: t('knowledge.documents.chapterExtraction'),
      description: {
        formats: t('knowledge.documents.chapterFormats'),
        method: t('knowledge.documents.chapterMethod'),
        description: t('knowledge.documents.chapterDescription'),
      },
      defaultOCR: false,
      img: chapterImg,
    },
    page: {
      label: t('knowledge.documents.pageExtraction'),
      description: {
        formats: t('knowledge.documents.pageFormats'),
        method: t('knowledge.documents.pageMethod'),
        description: t('knowledge.documents.pageDescription'),
      },
      defaultOCR: false,
      img: chapterImg,
    },
    worksheet: {
      label: t('knowledge.documents.worksheetExtraction'),
      description: {
        formats: t('knowledge.documents.worksheetFormats'),
        method: t('knowledge.documents.worksheetMethod'),
        description: t('knowledge.documents.worksheetDescription'),
      },
      defaultOCR: false,
      img: worksheetImg,
    },
    row: {
      label: t('knowledge.documents.rowExtraction'),
      description: {
        formats: t('knowledge.documents.rowFormats'),
        method: t('knowledge.documents.rowMethod'),
        description: t('knowledge.documents.rowDescription'),
      },
      defaultOCR: false,
      img: rowImg,
    },
  };

  // Get available extraction methods based on file extension
  // Word: fullText + chapter (default: chapter)
  // Excel: fullText + worksheet + row (default: row)  
  // PDF: fullText + page (default: page)
  // PPT: fullText + page (default: fullText)
  // Others: fullText only
  const getAvailableExtractionMethods = (extension: string) => {
    const ext = extension.toLowerCase();

    if (ext === 'ppt' || ext === 'pptx') {
      return {
        methods: ['fullText', 'page'],
        default: 'fullText',
      };
    } else if (ext === 'docx' || ext === 'doc') {
      return {
        methods: ['fullText', 'chapter'],
        default: 'chapter',
      };
    } else if (ext === 'xlsx' || ext === 'xls' || ext === 'csv') {
      return {
        methods: ['fullText', 'worksheet', 'row'],
        default: 'fullText',
      };
    } else if (ext === 'pdf') {
      return {
        methods: ['fullText', 'page'],
        default: 'page',
      };
    } else {
      return {
        methods: ['fullText'],
        default: 'fullText',
      };
    }
  };

  useEffect(() => {
    const fetchModels = async () => {
      try {
        const ocrData = await fetchOcrModels();
        setOcrModels(ocrData);
      } catch {
        message.error(t('common.fetchFailed'));
      } finally {
        setLoadingOcrModels(false);
      }
    };

    fetchModels();
  }, []);

  useEffect(() => {
    if (extractionConfig?.knowledge_document_list) {
      setKnowledgeDocumentList(extractionConfig.knowledge_document_list);
    }
  }, [extractionConfig]);

  // Generate table data from different sources
  const generateData = () => {
    if (extractionConfig?.knowledge_document_list) {
      return extractionConfig.knowledge_document_list.map((doc) => {
        const extension = doc.name?.split('.').pop()?.toLowerCase() || 'text';
        const availableMethods = getAvailableExtractionMethods(extension);
        const currentMethod = doc.parse_type || availableMethods.default;
        return {
          key: doc.id,
          name: doc.name,
          method: extractionMethods[currentMethod as keyof typeof extractionMethods]?.label || extractionMethods[availableMethods.default as keyof typeof extractionMethods]?.label,
          defaultMethod: currentMethod,
          extension,
        };
      });
    }

    if (type === 'web_page' && webLinkData) {
      return [
        {
          key: knowledgeDocumentIds[0] || 0,
          name: webLinkData.name,
          method: extractionMethods['fullText'].label,
          defaultMethod: 'fullText',
          extension: 'web',
        },
      ];
    }

    if (type === 'manual' && manualData) {
      return [
        {
          key: knowledgeDocumentIds[0] || 0,
          name: manualData.name,
          method: extractionMethods['fullText'].label,
          defaultMethod: 'fullText',
          extension: 'text',
        },
      ];
    }

    return fileList.map((file, index) => {
      const extension = file.name.split('.').pop()?.toLowerCase() || 'text';
      const availableMethods = getAvailableExtractionMethods(extension);
      return {
        key: knowledgeDocumentIds[index] || index,
        name: file.name,
        method: extractionMethods[availableMethods.default as keyof typeof extractionMethods].label,
        defaultMethod: availableMethods.default,
        extension,
      };
    });
  };

  const data = generateData();

  const [knowledgeDocumentList, setKnowledgeDocumentList] = useState<any[]>(
    extractionConfig?.knowledge_document_list
      ? extractionConfig.knowledge_document_list.map((doc) => ({
        id: doc.id,
        name: doc.name || '',
        enable_ocr_parse: doc.enable_ocr_parse,
        ocr_model: doc.ocr_model,
        parse_type: doc.parse_type,
      }))
      : generateData().map((item) => ({
        id: item.key,
        name: item.name,
        enable_ocr_parse: false,
        ocr_model: null,
        parse_type: item.defaultMethod,
      }))
  );

  const columns = [
    {
      title: t('knowledge.documents.name'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('knowledge.documents.extractMethod'),
      dataIndex: 'method',
      key: 'method',
    },
    {
      title: t('knowledge.documents.actions'),
      key: 'actions',
      render: (_: unknown, record: any, index: number) => (
        <Button 
          type="link" 
          onClick={() => handleConfigure(record, index)}
          disabled={loadingOcrModels}
          loading={loadingOcrModels}
        >
          {t('knowledge.documents.config')}
        </Button>
      ),
    },
  ];

  const handleConfigure = (record: { defaultMethod: keyof typeof extractionMethods; extension: string; [key: string]: any }, index: number) => {
    const documentConfig = knowledgeDocumentList[index];
    const paddleOCR = ocrModels.find((model) => model.name === 'PaddleOCR' && model.enabled);
    const firstEnabledModel = ocrModels.find((model) => model.enabled);
    const defaultModel = paddleOCR || firstEnabledModel;
    const availableMethods = getAvailableExtractionMethods(record.extension);

    setSelectedDocument({ ...record, index, availableMethods });
    setSelectedMethod(documentConfig?.parse_type || availableMethods.default);
    setOcrEnabled(
      (documentConfig?.enable_ocr_parse ?? extractionMethods[availableMethods.default as keyof typeof extractionMethods]?.defaultOCR) || false
    );
    
    let ocrModelToSelect = documentConfig?.ocr_model;
    if (extractionConfig && extractionConfig.knowledge_document_list) {
      const doc = extractionConfig.knowledge_document_list.find((d) => d.id === record.key);
      if (doc) {
        setSelectedMethod((doc.parse_type as any) || availableMethods.default);
        setOcrEnabled(doc.enable_ocr_parse);
        ocrModelToSelect = doc.ocr_model;
      }
    }
    setSelectedOcrModel(ocrModelToSelect || (defaultModel ? defaultModel.id : null));

    setModalVisible(true);
  };

  const closeModal = () => {
    setModalVisible(false);
    setSelectedDocument(null);
  };

  const handleMethodChange = (value: keyof typeof extractionMethods) => {
    setSelectedMethod(value);
    setOcrEnabled(extractionMethods[value]?.defaultOCR || false);
  };

  const handleConfirm = () => {
    const updatedConfig = {
      id: knowledgeDocumentList[selectedDocument.index]?.id,
      name: knowledgeDocumentList[selectedDocument.index]?.name,
      enable_ocr_parse: ocrEnabled,
      ocr_model: ocrEnabled ? selectedOcrModel : null,
      parse_type: selectedMethod || 'fullText',
    };

    const updatedList = [...knowledgeDocumentList];
    updatedList[selectedDocument.index] = updatedConfig;

    setKnowledgeDocumentList(updatedList);

    if (onConfigChange) {
      onConfigChange({
        knowledge_source_type: type || 'file',
        knowledge_document_list: updatedList,
      });
    }

    setModalVisible(false);
  };

  const handleCancel = () => {
    closeModal();
  };

  return (
    <div>
      <CustomTable columns={columns} dataSource={data} pagination={false} />
      <OperateModal
        width={650}
        visible={modalVisible}
        onCancel={handleCancel}
        title={t('knowledge.documents.selectExtractionMethod')}
        footer={
          <div className="text-right">
            <Button onClick={handleCancel} className="mr-4">
              {t('common.cancel')}
            </Button>
            <Button type="primary" onClick={handleConfirm}>
              {t('common.confirm')}
            </Button>
          </div>
        }
      >
        {selectedDocument && (
          <div className={styles.config}>
            <h3 className="mb-2 font-semibold">{t('knowledge.documents.extractMethod')}</h3>
            <Select
              style={{ width: '100%', marginBottom: '16px' }}
              value={selectedMethod}
              onChange={handleMethodChange}
            >
              {selectedDocument.availableMethods?.methods.map((methodKey: string) => (
                <Option key={methodKey} value={methodKey}>
                  {extractionMethods[methodKey as keyof typeof extractionMethods]?.label}
                </Option>
              ))}
            </Select>
            {selectedMethod && ['chapter', 'fullText'].includes(selectedMethod) && (
              <div className={`rounded-md p-4 mb-6 ${styles.configItem}`}>
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-sm font-semibold">{t('knowledge.documents.ocrEnhancement')}</h3>
                  <Switch
                    size="small"
                    checked={ocrEnabled}
                    onChange={(checked) => setOcrEnabled(checked)}
                  />
                </div>
                <p className={`${ocrEnabled ? 'mb-4' : ''} text-xs`}>{t('knowledge.documents.ocrEnhancementDesc')}</p>
                {ocrEnabled && (
                  <Form.Item className="mb-0" label={`OCR ${t('common.model')}`}>
                    <Select
                      style={{ width: '100%' }}
                      disabled={!ocrEnabled}
                      loading={loadingOcrModels}
                      value={allOcrModelsDisabled ? undefined : selectedOcrModel}
                      onChange={(value) => setSelectedOcrModel(value)}
                      placeholder={allOcrModelsDisabled ? t('knowledge.documents.ocrModelNotConfigured') : undefined}
                    >
                      {ocrModels.map((model) => (
                        <Option key={model.id} value={model.id} disabled={!model.enabled}>
                          {model.name}
                        </Option>
                      ))}
                    </Select>
                    {allOcrModelsDisabled && (
                      <Alert
                        className="mt-2"
                        type="warning"
                        showIcon
                        icon={<WarningOutlined />}
                        message={
                          <span>
                            {t('knowledge.documents.ocrModelNotConfiguredTip')}{' '}
                            <Link href="/opspilot/provider?tab=4" className="text-[var(--color-primary)]">
                              {t('knowledge.documents.modelConfig')}
                            </Link>
                          </span>
                        }
                      />
                    )}
                  </Form.Item>
                )}
              </div>
            )}
            <div>
              <h3 className="mb-2 font-semibold">{t('knowledge.documents.extractionDescription')}</h3>
              <div className="rounded-md p-4 border border-[var(--color-border-1)]">
                <h2 className="mb-2">{t('knowledge.documents.descriptionTitle')}</h2>
                <ul className="pl-[25px] list-disc text-xs text-[var(--color-text-3)] mb-4">
                  <li className="mb-2">
                    {t('knowledge.documents.formats')}: {selectedMethod ? extractionMethods[selectedMethod]?.description.formats : ''}
                  </li>
                  <li className="mb-2">
                    {t('knowledge.documents.method')}: {selectedMethod ? extractionMethods[selectedMethod]?.description.method : ''}
                  </li>
                  <li>
                    {t('knowledge.documents.introduction')}: {selectedMethod ? extractionMethods[selectedMethod]?.description.description : ''}
                  </li>
                </ul>
                <h2 className="mb-2">{t('knowledge.documents.example')}</h2>
                {selectedMethod && (
                  <div className="pl-[25px]">
                    <Image
                      src={
                        typeof extractionMethods[selectedMethod]?.img === 'string'
                          ? extractionMethods[selectedMethod]?.img
                          : extractionMethods[selectedMethod]?.img.src
                      }
                      alt="example"
                      className="rounded-md"
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </OperateModal>
    </div>
  );
};

export default ExtractionStep;
