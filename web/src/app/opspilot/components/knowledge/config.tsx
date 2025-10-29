import React, { useEffect, useState } from 'react';
import { Select, Slider, InputNumber, Input, message, Tooltip, Switch, Card, Radio } from 'antd';
import { ModelOption, ConfigDataProps, ConfigProps } from '@/app/opspilot/types/knowledge';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

const { Option } = Select;

const ConfigComponent: React.FC<ConfigProps> = ({ configData, setConfigData }) => {
  const { t } = useTranslation();
  const { fetchEmbeddingModels, fetchSemanticModels } = useKnowledgeApi();
  const [loadingModels, setLoadingModels] = useState<boolean>(true);
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const [rerankModelOptions, setRerankModelOptions] = useState<ModelOption[]>([]);

  const ragTypeConfigs = [
    {
      key: 'enableNaiveRag' as keyof ConfigDataProps,
      sizeKey: 'ragSize' as keyof ConfigDataProps,
      titleKey: 'knowledge.naiveRag'
    },
    {
      key: 'enableQaRag' as keyof ConfigDataProps,
      sizeKey: 'qaSize' as keyof ConfigDataProps,
      titleKey: 'knowledge.qaRag'
    },
    {
      key: 'enableGraphRag' as keyof ConfigDataProps,
      sizeKey: 'graphSize' as keyof ConfigDataProps,
      titleKey: 'knowledge.graphRag'
    }
  ];

  useEffect(() => {
    const fetchModels = async () => {
      try {
        const [rerankData, embedData] = await Promise.all([
          fetchSemanticModels(),
          fetchEmbeddingModels()
        ]);
        setModelOptions(embedData);
        setRerankModelOptions(rerankData);
      } catch {
        message.error(t('common.fetchFailed'));
      } finally {
        setLoadingModels(false);
      }
    };

    fetchModels();
  }, []);

  // Check if retrieval strategy section should be shown
  const shouldShowRetrievalStrategy = configData.enableNaiveRag || configData.enableQaRag;

  return (
    <>
      <div className="mb-4 flex items-center">
        <label className="block text-sm font-medium mb-1 w-32">{t('knowledge.embeddingModel')}</label>
        <Select
          className="flex-1"
          placeholder={`${t('common.inputMsg')}${t('knowledge.embeddingModel')}`}
          disabled
          loading={loadingModels}
          value={configData.selectedEmbedModel}
          showSearch
          filterOption={(input, option) =>
            typeof option?.children === 'string' && (option.children as string).toLowerCase().includes(input.toLowerCase())
          }
          onChange={(value) => setConfigData(prevData => ({ ...prevData, selectedEmbedModel: value }))}
        >
          {modelOptions.map((model) => (
            <Option key={model.id} value={model.id} disabled={!model.enabled}>
              {model.name}
            </Option>
          ))}
        </Select>
      </div>
      <div className="mb-4 flex">
        <label className="block text-sm font-medium mb-1 w-32">{t('knowledge.retrievalSetting')}</label>
        <div className="flex-1">
          <p className="mb-2">{t('knowledge.returnedType')}</p>
          <div className="flex gap-4 mb-4">
            {ragTypeConfigs.map(config => (
              <div
                key={config.key}
                className={`relative flex-1 px-4 py-2 pb-0 border rounded-md cursor-pointer transition-all duration-200 overflow-hidden ${
                  configData[config.key] 
                    ? 'shadow-sm' 
                    : 'hover:shadow-sm'
                }`}
                onClick={() => setConfigData(prevData => ({ ...prevData, [config.key]: !prevData[config.key] }))}
              >
                {configData[config.key] && (
                  <div className="absolute top-0 right-0 w-6 h-6">
                    <div 
                      className="absolute top-0 right-0"
                      style={{
                        width: '0',
                        height: '0',
                        borderLeft: '24px solid transparent',
                        borderTop: '24px solid #3b82f6'
                      }}
                    />
                    <div className="absolute top-0 right-1">
                      <svg 
                        className="w-3 h-3 text-white"
                        fill="currentColor"
                        viewBox="0 0 16 16"
                      >
                        <path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/>
                      </svg>
                    </div>
                  </div>
                )}
                
                <div className="mb-3">
                  <h3 className={`font-medium text-sm transition-colors duration-200 ${
                    configData[config.key] ? 'text-gray-700' : 'text-gray-700'
                  }`}>
                    {t(config.titleKey)}
                  </h3>
                </div>
                <div className="mb-2">
                  <label className="block text-xs mb-2 relative">
                    {t('knowledge.chunkCount')}
                    <Tooltip title={`${t('knowledge.chunkCountTip')}`}>
                      <QuestionCircleOutlined className="ml-1 cursor-pointer"/>
                    </Tooltip>
                  </label>
                  <InputNumber
                    size="small"
                    className='w-full'
                    min={0}
                    value={typeof configData[config.sizeKey] === 'number' ? (configData[config.sizeKey] as number) : undefined}
                    onChange={(value) => setConfigData(prevData => ({...prevData, [config.sizeKey]: value ?? 0}))}
                    onClick={(e) => e.stopPropagation()}
                  />
                </div>
              </div>
            ))}
          </div>
          
          {/* Conditional Retrieval Strategy Section */}
          {shouldShowRetrievalStrategy && (
            <div className="p-4 pb-0 border rounded-md mb-4">
              <h3 className="font-medium text-sm mb-4">{t('knowledge.retrievalStrategy')}</h3>
              <div className="flex gap-4 mb-4">
                <Card
                  size="small"
                  className={`flex-1 cursor-pointer transition-all duration-200 ${
                    configData.searchType === 'mmr' 
                      ? 'border-blue-500 shadow-sm' 
                      : 'hover:shadow-sm'
                  }`}
                  onClick={() => setConfigData(prevData => ({ ...prevData, searchType: 'mmr' }))}
                >
                  <div className="text-center">
                    <h4 className="font-medium text-sm mb-2">MMR</h4>
                    <p className="text-xs text-gray-500">{t('knowledge.mmrDesc')}</p>
                  </div>
                </Card>
                <Card
                  size="small"
                  className={`flex-1 cursor-pointer transition-all duration-200 ${
                    configData.searchType === 'similarity_score_threshold' 
                      ? 'border-blue-500 shadow-sm' 
                      : 'hover:shadow-sm'
                  }`}
                  onClick={() => setConfigData(prevData => ({ ...prevData, searchType: 'similarity_score_threshold' }))}
                >
                  <div className="text-center">
                    <h4 className="font-medium text-sm mb-2">{t('knowledge.threshold')}</h4>
                    <p className="text-xs text-gray-500">{t('knowledge.thresholdDesc')}</p>
                  </div>
                </Card>
              </div>
              
              {configData.searchType === 'similarity_score_threshold' && (
                <div className="flex items-center justify-between mb-4">
                  <label className="text-sm w-[80px]">{t('knowledge.threshold')}</label>
                  <div className='flex flex-1 items-center gap-4'>
                    <Slider
                      className="flex-1"
                      min={0}
                      max={1}
                      step={0.01}
                      value={configData.scoreThreshold}
                      onChange={(value) => setConfigData(prevData => ({ ...prevData, scoreThreshold: value }))}
                    />
                    <Input className="w-14" value={configData.scoreThreshold.toFixed(2)} readOnly />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      {/* Conditional Recall Method Section */}
      {configData.enableNaiveRag && (
        <div className="mb-4 flex items-center">
          <label className="block text-sm font-medium mb-1 w-32">{t('knowledge.recallMethod')}</label>
          <Radio.Group
            className="flex-1"
            value={configData.ragRecallMode}
            onChange={(e) => setConfigData(prevData => ({ ...prevData, ragRecallMode: e.target.value }))}
          >
            <Radio value="chunk">{t('knowledge.recallByChunk')}</Radio>
            <Radio value="segment">{t('knowledge.recallBySegment')}</Radio>
          </Radio.Group>
        </div>
      )}
      <div className="mb-4 flex">
        <label className="block text-sm font-medium mb-1 w-32">{t('knowledge.rerankSettings')}</label>
        <div className="flex-1">
          <div className="p-4 pb-0 border rounded-md mb-4">
            <div className="flex items-center justify-between mb-4">
              <label className="font-medium text-sm">{t('knowledge.rerankModel')}</label>
              <Switch
                size="small"
                checked={configData.rerankModel}
                onChange={(checked) => setConfigData(prevData => ({ ...prevData, rerankModel: checked, selectedRerankModel: null }))}
              />
            </div>
            <p className="text-xs mb-4 text-[var(--color-text-4)]">{t('knowledge.rerankModelDesc')}</p>
            {configData.rerankModel && (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <Select
                    className="flex-1"
                    placeholder={`${t('common.selectMsg')}${t('knowledge.rerankModel')}`}
                    loading={loadingModels}
                    value={configData.selectedRerankModel}
                    showSearch
                    filterOption={(input, option) =>
                      typeof option?.children === 'string' && (option.children as string).toLowerCase().includes(input.toLowerCase())
                    }
                    onChange={(value) => setConfigData(prevData => ({ ...prevData, selectedRerankModel: value }))}
                  >
                    {rerankModelOptions.map((model) => (
                      <Option key={model.id} value={model.id} disabled={!model.enabled}>
                        {model.name}
                      </Option>
                    ))}
                  </Select>
                </div>
                <div className="flex items-center justify-between mb-4">
                  <label className="text-sm w-[100px]">{t('knowledge.rerankChunkCount')}</label>
                  <InputNumber
                    className='flex-1'
                    min={1}
                    value={configData.rerankTopK}
                    onChange={(value) => setConfigData(prevData => ({ ...prevData, rerankTopK: value ?? 1 }))}
                    style={{ width: '100%' }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
};

export default ConfigComponent;
