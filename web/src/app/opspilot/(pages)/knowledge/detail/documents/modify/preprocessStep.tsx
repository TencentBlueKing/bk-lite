import React, { useState, useEffect } from 'react';
import { Card, InputNumber, Select, Form, Button, Empty, Skeleton, List, Image } from 'antd';
import styles from './modify.module.scss';
import type { StaticImageData } from 'next/image';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import { useLocale } from '@/context/locale';
import ContentDrawer from '@/components/content-drawer';
import useContentDrawer from '@/app/opspilot/hooks/useContentDrawer';
import { PreviewData } from '@/app/opspilot/types/knowledge';
import fixedImg from '@/app/opspilot/img/fixed_chunk.png';
import overlapImg from '@/app/opspilot/img/overlap_chunk.png';
import semanticImgEn from '@/app/opspilot/img/semantic_chunk-en.png';
import semanticImgZh from '@/app/opspilot/img/semantic_chunk-zh.png';
import noneImg from '@/app/opspilot/img/none_chunk.png';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

const { Option } = Select;

const PreprocessStep: React.FC<{
  knowledgeSourceType: string | null;
  knowledgeDocumentIds: number[];
  onConfigChange: (config: any) => void;
  initialConfig: any;
}> = ({ knowledgeSourceType, knowledgeDocumentIds, onConfigChange, initialConfig }) => {
  const { t } = useTranslation();
  const { locale } = useLocale();

  const chunkTypes: Array<{
    key: keyof typeof chunkImages;
    title: string;
    desc: string;
    icon: string;
  }> = [
    { 
      key: 'fixed_size',
      title: t('knowledge.documents.fixedChunk'), 
      desc: t('knowledge.documents.fixedChunkDesc'), 
      icon: 'fenge' 
    },
    { 
      key: 'recursive',
      title: t('knowledge.documents.overlapChunk'),
      desc: t('knowledge.documents.overlapChunkDesc'), 
      icon: 'paichuzhongdie' 
    },
    { 
      key: 'semantic', 
      title: t('knowledge.documents.semanticChunk'),
      desc: t('knowledge.documents.semanticChunkDesc'), 
      icon: 'yuyirenwu' 
    },
    // { 
    //   key: 'full', 
    //   title: t('knowledge.documents.noChunk'), 
    //   desc: t('knowledge.documents.noChunkDesc'), 
    //   icon: 'fenge1' 
    // },
  ];

  const [chunkType, setChunkType] = useState<keyof typeof chunkImages>(
    initialConfig.chunk_type || chunkTypes[0].key
  );
  const [formData, setFormData] = useState({
    chunkSize: initialConfig?.general_parse_chunk_size || 200,
    chunkOverlap: initialConfig?.general_parse_chunk_overlap || 50,
    semanticModel: initialConfig?.semantic_chunk_parse_embedding_model || null,
  });
  const [previewData, setPreviewData] = useState<PreviewData[]>([]);
  const [loadingPreview, setLoadingPreview] = useState<boolean>(false);

  const {
    drawerVisible,
    drawerContent,
    showDrawer,
    hideDrawer,
  } = useContentDrawer();

  const chunkImages = {
    fixed_size: fixedImg,
    recursive: overlapImg,
    semantic: locale === 'en' ? semanticImgEn : semanticImgZh,
    full: noneImg,
  };

  const chunkIntrdution = {
    fixed_size: 'fixed',
    recursive: 'overlap',
    semantic: 'semantic',
    full: 'none',
  };

  const { previewChunk, fetchEmbeddingModels } = useKnowledgeApi();
  const [embeddingModels, setEmbeddingModels] = useState<{ id: string; name: string }[]>([]);
  const [loadingModels, setLoadingModels] = useState<boolean>(true);

  useEffect(() => {
    const fetchModels = async () => {
      try {
        const models = await fetchEmbeddingModels();
        setEmbeddingModels(models);
      } catch {
        setEmbeddingModels([]);
      } finally {
        setLoadingModels(false);
      }
    };

    fetchModels();
  }, []);

  const updateConfig = (updates: Partial<typeof formData> & { chunkType?: keyof typeof chunkImages }) => {
    const newChunkType = updates.chunkType ?? chunkType;
    const updatedFormData = {
      chunkSize: updates.chunkType ? 200 : formData.chunkSize,
      chunkOverlap: updates.chunkType ? 0 : formData.chunkOverlap,
      semanticModel: updates.chunkType ? null : formData.semanticModel,
      ...updates,
    };

    setChunkType(newChunkType);
    setFormData(updatedFormData);

    onConfigChange({
      knowledge_source_type: knowledgeSourceType,
      knowledge_document_list: knowledgeDocumentIds,
      general_parse_chunk_size: updatedFormData.chunkSize,
      general_parse_chunk_overlap: updatedFormData.chunkOverlap,
      semantic_chunk_parse_embedding_model: updatedFormData.semanticModel,
      chunk_type: newChunkType,
    });
  };
  
  const handleChunkTypeChange = (type: keyof typeof chunkImages) => {
    updateConfig({ chunkType: type });
  };
  
  const handleChange = (field: string, value: any) => {
    updateConfig({ [field]: value });
  };

  const handlePreviewClick = async () => {
    if (!knowledgeDocumentIds.length) return;

    setLoadingPreview(true);
    try {
      const data = await previewChunk({
        knowledge_source_type: knowledgeSourceType || 'file',
        knowledge_document_id: knowledgeDocumentIds[0],
        general_parse_chunk_size: formData.chunkSize,
        general_parse_chunk_overlap: formData.chunkOverlap,
        semantic_chunk_parse_embedding_model: formData.semanticModel,
        chunk_type: chunkType,
      });

      const processedData = data.map((content: string, index: number) => ({
        id: index,
        content,
        characters: content.length,
      }));

      setPreviewData(processedData);
    } catch {
      setPreviewData([]);
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleContentClick = (content: string) => {
    showDrawer(content);
  };

  return (
    <div>
      <div className="grid grid-cols-3 gap-4 mb-6">
        {chunkTypes.map((type) => (
          <Card
            key={type.key}
            className={`${styles.chunkCard} ${chunkType === type.key ? `${styles.active} border-2 border-blue-500 bg-blue-100` : ''}`}
            onClick={() => handleChunkTypeChange(type.key)}
          >
            <div className="flex items-center mb-2">
              <Icon type={type.icon} className="text-2xl mr-2" />
              <h3 className="text-sm font-semibold">{type.title}</h3>
            </div>
            <p className="text-xs text-[var(--color-text-3)]">{type.desc}</p>
          </Card>
        ))}
      </div>
      <div className="flex justify-between">
        <div className={`flex-1 w-0 pr-4 ${styles.config}`}>
          {chunkType !== 'full' && (
            <>
              <h2 className="text-sm font-semibold mb-3">{t('knowledge.documents.chunkParams')}</h2>
              <div className={`rounded-md p-4 mb-6 ${styles.configItem}`}>
                {chunkType === 'fixed_size' && (
                  <Form layout="vertical">
                    <Form.Item label={t('knowledge.documents.chunkSizeLabel')}>
                      <InputNumber
                        style={{ width: '100%' }}
                        min={0}
                        value={formData.chunkSize}
                        onChange={(value) => handleChange('chunkSize', value)}
                      />
                    </Form.Item>
                  </Form>
                )}
                {chunkType === 'recursive' && (
                  <Form layout="vertical">
                    <Form.Item label={t('knowledge.documents.chunkSizeLabel')}>
                      <InputNumber
                        style={{ width: '100%' }}
                        min={0}
                        value={formData.chunkSize}
                        onChange={(value) => handleChange('chunkSize', value)}
                      />
                    </Form.Item>
                    <Form.Item label={t('knowledge.documents.chunkOverlap')}>
                      <InputNumber
                        style={{ width: '100%' }}
                        min={0}
                        value={formData.chunkOverlap}
                        onChange={(value) => handleChange('chunkOverlap', value)}
                      />
                    </Form.Item>
                  </Form>
                )}
                {chunkType === 'semantic' && (
                  <Form.Item label={t('common.model')}>
                    <Select
                      style={{ width: '100%' }}
                      value={formData.semanticModel}
                      onChange={(value) => handleChange('semanticModel', value)}
                      loading={loadingModels}
                    >
                      {embeddingModels.map((model) => (
                        <Option key={model.id} value={model.id}>
                          {model.name}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                )}
              </div>
            </>
          )}
          <h2 className="text-sm font-semibold mb-3">{t('knowledge.documents.chunkIllustration')}</h2>
          <div className={`rounded-md p-4 mb-6 ${styles.configItem}`}>
            <h2 className="mb-2">{t('knowledge.documents.descriptionTitle')}</h2>
            <ul className="pl-[25px] list-disc text-xs text-[var(--color-text-3)] mb-4">
              <li className="mb-2">
                {t('knowledge.documents.formats')}: {t(`knowledge.documents.${chunkIntrdution[chunkType]}Formats`)}
              </li>
              <li className="mb-2">
                {t('knowledge.documents.method')}: {t(`knowledge.documents.${chunkIntrdution[chunkType]}Method`)}
              </li>
              <li>
                {t('knowledge.documents.introduction')}: {t(`knowledge.documents.${chunkIntrdution[chunkType]}Description`)}
              </li>
            </ul>
            <h2 className="mb-2">{t('knowledge.documents.example')}</h2>
            <div className="pl-[25px]">
              <Image
                src={
                  typeof chunkImages[chunkType] === 'string'
                    ? chunkImages[chunkType]
                    : (chunkImages[chunkType] as StaticImageData)?.src || noneImg.src
                }
                alt="example"
                className="rounded-md"
              />
            </div>
          </div>
        </div>

        <div className="flex-1 w-0">
          <div className="flex justify-between">
            <h2 className="text-sm font-semibold mb-3">{t('knowledge.documents.preview')}</h2>
            <Button type="primary" size="small" onClick={handlePreviewClick} loading={loadingPreview}>
              {t('knowledge.documents.viewChunk')}
            </Button>
          </div>
          {loadingPreview ? (
            <List
              itemLayout="vertical"
              dataSource={[1, 2, 3]}
              renderItem={() => (
                <List.Item>
                  <Skeleton active />
                </List.Item>
              )}
            />
          ) : previewData.length > 0 ? (
            previewData.map((item) => (
              <div key={item.id} className={`rounded-md p-4 mb-3 ${styles.previewItem}`} onClick={() => handleContentClick(item.content)}>
                <div className="flex justify-between items-center mb-2">
                  <span className={`text-xs flex items-center ${styles.number}`}>#{item.id?.toString().padStart(3, '0')}</span>
                  <span className="flex items-center text-sm">
                    <Icon type="zifu" className="text-xl pr-1" />
                    {item.characters} {t('knowledge.documents.characters')}
                  </span>
                </div>
                <div>
                  <p>{item.content}</p>
                </div>
              </div>
            ))
          ) : (
            <Empty description={t('common.noResult')} />
          )}
        </div>
        <ContentDrawer visible={drawerVisible} onClose={hideDrawer} content={drawerContent} />
      </div>
    </div>
  );
};

export default PreprocessStep;
