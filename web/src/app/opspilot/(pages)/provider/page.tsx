'use client';

import React, { useState, useEffect } from 'react';
import { Segmented, message, Input, Spin, Button } from 'antd';
import { useProviderApi } from '@/app/opspilot/api/provider';
import ProviderGrid from '@/app/opspilot/components/provider/grid';
import ConfigModal from '@/app/opspilot/components/provider/configModal';
import { Model, TabConfig } from '@/app/opspilot/types/provider';
import styles from '@/app/opspilot/styles/common.module.scss';
import { MODEL_TYPE_OPTIONS, CONFIG_MAP } from '@/app/opspilot/constants/provider';
import { useTranslation } from '@/utils/i18n';

const { Search } = Input;

const tabConfig: TabConfig[] = [
  { key: '1', label: 'LLM Model', type: 'llm_model' },
  { key: '2', label: 'Embed Model', type: 'embed_provider' },
  { key: '3', label: 'Rerank Model', type: 'rerank_provider' },
  { key: '4', label: 'OCR Model', type: 'ocr_provider' },
];

const ProviderPage: React.FC = () => {
  const { t } = useTranslation();
  const { fetchModels, addProvider } = useProviderApi();
  const [models, setModels] = useState<Model[]>([]);
  const [filteredModels, setFilteredModels] = useState<Model[]>([]);
  const [isAddModalVisible, setIsAddModalVisible] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [modalLoading, setModalLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<string>('1');

  const fetchModelsData = async (type: string) => {
    setLoading(true);
    try {
      const data = await fetchModels(type);
      const mappedData = Array.isArray(data)
        ? data.map((model) => ({ ...model, id: Number(model.id) }))
        : [];
      setModels(mappedData);
      setFilteredModels(mappedData);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchModelsData('llm_model');
  }, []);

  const handleSegmentedChange = (key: string) => {
    setModels([]);
    setFilteredModels([]);
    setActiveTab(key);
    const tab = tabConfig.find((t) => t.key === key);
    if (tab) {
      fetchModelsData(tab.type);
    }
  };

  const handleSearch = (value: string) => {
    const term = value.toLowerCase();
    if (term === '') {
      setFilteredModels(models);
    } else {
      setFilteredModels(
        models.filter((model) =>
          model.name?.toLowerCase().includes(term)
        )
      );
    }
  };
  
  const handleAddProvider = async (values: any) => {
    const type = tabConfig.find((tab) => tab.key === activeTab)?.type || '';
    const configField = CONFIG_MAP[type];

    const payload: any = {
      name: values.name,
      llm_model_type: values.type,
      enabled: values.enabled,
      team: values.team,
      consumer_team: values.consumer_team,
    };

    switch (type) {
      case 'llm_model':
        payload.llm_config = {
          model: values.modelName,
          openai_api_key: values.apiKey,
          openai_base_url: values.url,
        };
        break;
      case 'embed_provider':
        payload.embed_model_type = "lang-serve";
      case 'rerank_provider':
        if (type === 'rerank_provider') {
          payload.rerank_model_type = "langserve";
        }
        payload[configField] = {
          model: values.modelName,
          base_url: values.url,
          api_key: values.apiKey,
        };
        break;
      default:
        if (configField) {
          payload[configField] = {
            base_url: values.url,
            api_key: values.apiKey,
          };
        }
        break;
    }

    setModalLoading(true);
    try {
      const result = await addProvider(type, payload);
      if (result && result.id) {
        message.success(t('common.saveSuccess'));
        fetchModelsData(type);
        setIsAddModalVisible(false);
      } else {
        message.error(t('common.saveFailed'));
      }
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const getCategorizedModels = () => {
    const categorizedModels: Record<string, Model[]> = {};
    filteredModels.forEach((model) => {
      const type = model.llm_model_type || 'Unknown';
      if (!categorizedModels[type]) {
        categorizedModels[type] = [];
      }
      categorizedModels[type].push(model);
    });
    return categorizedModels;
  };

  return (
    <div className={`w-full h-full ${styles.segmented}`}>
      <Segmented
        options={tabConfig.map((tab) => ({label: tab.label, value: tab.key}))}
        value={activeTab}
        onChange={handleSegmentedChange}
        className="mb-4"
      />
      <div className="flex justify-end mb-4">
        <Search
          allowClear
          enterButton
          placeholder={`${t('common.search')}...`}
          className="w-60"
          onSearch={handleSearch}
        />
        {activeTab !== '4' && (
          <Button type="primary" className="ml-2" onClick={() => setIsAddModalVisible(true)}>
            {t('common.add')}
          </Button>
        )}
      </div>
      <Spin spinning={loading}>
        {activeTab === '1' ? (
          Object.entries(getCategorizedModels()).map(([type, models]) => (
            <div key={type} className="mb-4">
              <h3 className="font-semibold mb-4">{MODEL_TYPE_OPTIONS[type]}</h3>
              <ProviderGrid
                models={models}
                filterType="llm_model"
                loading={loading}
                setModels={(updatedModels) => {
                  setModels(updatedModels);
                  setFilteredModels(updatedModels);
                }}
              />
            </div>
          ))
        ) : (
          <ProviderGrid
            models={filteredModels}
            filterType={tabConfig.find((tab) => tab.key === activeTab)?.type || ''}
            loading={loading}
            setModels={(updatedModels) => {
              setModels(updatedModels);
              setFilteredModels(updatedModels);
            }}
          />
        )}
      </Spin>
      <ConfigModal
        visible={isAddModalVisible}
        mode="add"
        filterType={tabConfig.find((tab) => tab.key === activeTab)?.type || ''}
        confirmLoading={modalLoading}
        onOk={handleAddProvider}
        onCancel={() => setIsAddModalVisible(false)}
      />
    </div>
  );
};

export default ProviderPage;
