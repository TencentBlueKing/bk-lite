import React, { useState, useEffect } from 'react';
import { Button, Select, Switch, Form, message, Image } from 'antd';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import styles from './modify.module.scss';
import { ModelOption } from '@/app/opspilot/types/knowledge';
import { getDefaultExtractionMethod } from '@/app/opspilot/utils/extractionUtils';
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

  // Extracted data generation logic into a function
  const generateData = () => {
    if (extractionConfig?.knowledge_document_list) {
      return extractionConfig.knowledge_document_list.map((doc) => {
        const extension = doc.name?.split('.').pop()?.toLowerCase() || 'text';
        return {
          key: doc.id,
          name: doc.name,
          method: extractionMethods[doc.parse_type as keyof typeof extractionMethods]?.label || extractionMethods[getDefaultExtractionMethod(extension) as keyof typeof extractionMethods]?.label,
          defaultMethod: doc.parse_type || 'fullText',
        };
      });
    }

    if (type === 'web_page' && webLinkData) {
      return [{
        key: knowledgeDocumentIds[0] || 0,
        name: webLinkData.name,
        method: extractionMethods['fullText'].label,
        defaultMethod: 'fullText',
      }];
    }

    if (type === 'manual' && manualData) {
      return [{
        key: knowledgeDocumentIds[0] || 0,
        name: manualData.name,
        method: extractionMethods['fullText'].label,
        defaultMethod: 'fullText',
      }];
    }

    return fileList.map((file, index) => {
      const extension = file.name.split('.').pop()?.toLowerCase() || 'text';
      const defaultMethod = getDefaultExtractionMethod(extension);
      return {
        key: knowledgeDocumentIds[index] || index,
        name: file.name,
        method: extractionMethods[defaultMethod as keyof typeof extractionMethods].label,
        defaultMethod,
      };
    });
  };

  const data = generateData(); // Use the extracted function

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
        <Button type="link" onClick={() => handleConfigure(record, index)}>
          {t('knowledge.documents.config')}
        </Button>
      ),
    },
  ];

  const handleConfigure = (record: { defaultMethod: keyof typeof extractionMethods; [key: string]: any }, index: number) => {
    const documentConfig = knowledgeDocumentList[index];
    const defaultModel = ocrModels.find(model => model.name === 'PaddleOCR');

    setSelectedDocument({ ...record, index });
    setSelectedMethod(documentConfig?.parse_type || record.defaultMethod);
    setOcrEnabled((documentConfig?.enable_ocr_parse ?? extractionMethods[record.defaultMethod]?.defaultOCR) || false);
    setSelectedOcrModel(documentConfig?.ocr_model || (defaultModel ? defaultModel.id : null));

    if (extractionConfig && extractionConfig.knowledge_document_list) {
      const doc = extractionConfig.knowledge_document_list.find((d) => d.id === record.key);
      if (doc) {
        setSelectedMethod(record.defaultMethod);
        setOcrEnabled(doc.enable_ocr_parse);
        setSelectedOcrModel(doc.ocr_model);
      }
    }

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
    console.log('Updated knowledge document list:', updatedList);

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
              {Object.entries(extractionMethods).map(([key, method]) => (
                <Option key={key} value={key}>
                  {method.label}
                </Option>
              ))}
            </Select>
            {selectedMethod === 'fullText' && (
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
                      value={selectedOcrModel}
                      onChange={(value) => setSelectedOcrModel(value)}
                    >
                      {ocrModels.map((model) => (
                        <Option key={model.id} value={model.id} disabled={!model.enabled}>
                          {model.name}
                        </Option>
                      ))}
                    </Select>
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
                      src={typeof extractionMethods[selectedMethod]?.img === 'string' 
                        ? extractionMethods[selectedMethod]?.img 
                        : extractionMethods[selectedMethod]?.img.src}
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
