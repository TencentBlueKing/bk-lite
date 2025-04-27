import React, { useEffect, useState } from 'react';
import { Select, Switch, Slider, InputNumber, Input, Radio, message, Tooltip } from 'antd';
import { ModelOption, ConfigDataProps } from '@/app/opspilot/types/knowledge';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

const { Option } = Select;

interface ConfigProps {
  configData: ConfigDataProps;
  setConfigData: React.Dispatch<React.SetStateAction<ConfigDataProps>>;
}

const ConfigComponent: React.FC<ConfigProps> = ({ configData, setConfigData }) => {
  const { t } = useTranslation();
  const { fetchEmbeddingModels, fetchSemanticModels } = useKnowledgeApi();
  const [loadingModels, setLoadingModels] = useState<boolean>(true);
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const [rerankModelOptions, setRerankModelOptions] = useState<ModelOption[]>([]);

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

  const handleSearchTypeChange = (type: string) => {
    setConfigData(prevData => ({
      ...prevData,
      selectedSearchTypes: prevData.selectedSearchTypes.includes(type)
        ? prevData.selectedSearchTypes.filter(t => t !== type)
        : [...prevData.selectedSearchTypes, type]
    }));
  };

  const handlePatternChange = (e: any) => {
    setConfigData(prevData => ({
      ...prevData,
      textSearchMode: e.target.value
    }));
  };

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
          <div className="p-4 pb-0 border rounded-md mb-4">
            <div className="flex items-center mb-4 justify-between">
              <h3 className="font-medium text-sm">{t('knowledge.textSearch')}</h3>
              <Switch
                size="small"
                checked={configData.selectedSearchTypes.includes('textSearch')}
                onChange={() => handleSearchTypeChange('textSearch')}
              />

            </div>
            <p className="text-xs mb-4 text-[var(--color-text-4)]">
              {t('knowledge.textSearchDesc')}
            </p>
            {configData.selectedSearchTypes.includes('textSearch') && (
              <>
                <div className="flex items-center justify-between mb-4">
                  <label className="text-sm w-[100px]">{t('knowledge.pattern')}</label>
                  <Radio.Group
                    onChange={handlePatternChange}
                    value={configData.textSearchMode}
                    className="flex-1"
                  >
                    <Radio value="match">{t('knowledge.match')}</Radio>
                    <Radio value="match_phrase">{t('knowledge.matchPhrase')}</Radio>
                  </Radio.Group>
                </div>
                <div className="flex items-center justify-between mb-4">
                  <label className="text-sm w-[100px]">{t('knowledge.weight')}</label>
                  <div className="flex flex-1 items-center gap-4">
                    <Slider
                      className="flex-1"
                      min={0}
                      max={1}
                      step={0.01}
                      value={configData.textSearchWeight}
                      onChange={(value) => setConfigData(prevData => ({ ...prevData, textSearchWeight: value }))}
                    />
                    <Input className="w-14" value={configData.textSearchWeight.toFixed(2)} readOnly />
                  </div>
                </div>
              </>
            )}
          </div>
          <div className="p-4 pb-0 border rounded-md mb-4">
            <div className="flex items-center mb-4 justify-between">
              <h3 className="font-medium text-sm">{t('knowledge.vectorSearch')}</h3>
              <Switch
                size="small"
                checked={configData.selectedSearchTypes.includes('vectorSearch')}
                onChange={() => handleSearchTypeChange('vectorSearch')}
              />
            </div>
            <p className="text-xs mb-4 text-[var(--color-text-4)]">
              {t('knowledge.vectorSearchDesc')}
            </p>
            {configData.selectedSearchTypes.includes('vectorSearch') && (
              <>
                <div className="flex items-center justify-between mb-4">
                  <label className="text-sm w-[100px]">{t('knowledge.weight')}</label>
                  <div className='flex flex-1 items-center gap-4'>
                    <Slider
                      className="flex-1"
                      min={0}
                      max={1}
                      step={0.01}
                      value={configData.vectorSearchWeight}
                      onChange={(value) => setConfigData(prevData => ({ ...prevData, vectorSearchWeight: value }))}
                    />
                    <Input className="w-14" value={configData.vectorSearchWeight.toFixed(2)} readOnly />
                  </div>
                </div>
                <div className="flex items-center justify-between mb-4">
                  <label className="text-sm w-[100px]">{t('knowledge.returnQuantity')}</label>
                  <InputNumber
                    className='flex-1'
                    min={1}
                    value={configData.quantity}
                    onChange={(value) => setConfigData(prevData => ({ ...prevData, quantity: value ?? 1 }))}
                    style={{ width: '100%' }}
                  />
                </div>
                <div className="flex items-center justify-between mb-4">
                  <label className="text-sm w-[100px]">{t('knowledge.candidateQuantity')}</label>
                  <InputNumber
                    className='flex-1'
                    min={1}
                    value={configData.candidate}
                    onChange={(value) => setConfigData(prevData => ({ ...prevData, candidate: value ?? 1 }))}
                    style={{ width: '100%' }}
                  />
                </div>
              </>
            )}
          </div>
          <div className="flex items-center justify-between mb-4">
            <label className="text-sm w-[100px] relative mr-4">
              {t('knowledge.chunkCount')}
              <Tooltip title={`${t('knowledge.chunkCountTip')}`}>
                <QuestionCircleOutlined className="absolute top-0 right-0 -mt-1 -mr-1 cursor-pointer"/>
              </Tooltip>
            </label>
            <InputNumber
              className='flex-1'
              min={0}
              value={configData.resultCount}
              onChange={(value) => setConfigData(prevData => ({...prevData, resultCount: value}))}
              style={{width: '100%'}}
            />
          </div>
        </div>
      </div>
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
