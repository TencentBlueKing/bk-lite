'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Segmented, message, Input, Button, Select } from 'antd';
import { useProviderApi } from '@/app/opspilot/api/provider';
import ProviderGrid from '@/app/opspilot/components/provider/grid';
import ConfigModal from '@/app/opspilot/components/provider/configModal';
import ModelTree from '@/app/opspilot/components/provider/modelTree';
import styles from '@/app/opspilot/styles/common.module.scss';
import ModelGroupModal from '@/app/opspilot/components/provider/modelGroupModal';
import { Model, TabConfig, ModelGroup } from '@/app/opspilot/types/provider';
import { CONFIG_MAP, getProviderType, MODEL_CATEGORY_OPTIONS } from '@/app/opspilot/constants/provider';
import { useTranslation } from '@/utils/i18n';
import { ProviderGridSkeleton } from '@/app/opspilot/components/provider/skeleton';

const { Search } = Input;

const tabConfig: TabConfig[] = [
  { key: '1', label: 'LLM Model', type: 'llm_model' },
  { key: '2', label: 'Embed Model', type: 'embed_provider' },
  { key: '3', label: 'Rerank Model', type: 'rerank_provider' },
  { key: '4', label: 'OCR Model', type: 'ocr_provider' },
];

const ProviderPage: React.FC = () => {
  const { t } = useTranslation();
  const { 
    fetchModels, 
    addProvider, 
    fetchModelGroups,
    createModelGroup, 
    updateModelGroup, 
    deleteModelGroup, 
    updateGroupOrder 
  } = useProviderApi();
  
  const [models, setModels] = useState<Model[]>([]);
  const [filteredModels, setFilteredModels] = useState<Model[]>([]);
  const [modelGroups, setModelGroups] = useState<ModelGroup[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string>('all');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  
  const [isAddModalVisible, setIsAddModalVisible] = useState<boolean>(false);
  const [isGroupModalVisible, setIsGroupModalVisible] = useState<boolean>(false);
  const [groupModalMode, setGroupModalMode] = useState<'add' | 'edit'>('add');
  const [editingGroup, setEditingGroup] = useState<ModelGroup | null>(null);
  
  const [loading, setLoading] = useState<boolean>(false);
  const [modalLoading, setModalLoading] = useState<boolean>(false);
  const [groupModalLoading, setGroupModalLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<string>('1');
  
  const currentRequestId = useRef<string | null>(null);

  // Fetch model groups data by provider type
  const fetchModelGroupsData = async (providerType?: string) => {
    try {
      const groupsData = await fetchModelGroups('', providerType);
      // Transform API response to ModelGroup format
      const processedGroups: ModelGroup[] = groupsData.map((group: any) => ({
        id: group.id,
        name: group.name,
        display_name: group.display_name,
        icon: group.icon,
        count: group.model_count || 0, // Use model_count from API response
        is_build_in: group.is_build_in || false,
        index: group.index || 0,
        models: [],
        tags: group.tags || [],
      }));
      
      // Sort by index field
      processedGroups.sort((a, b) => (a.index || 0) - (b.index || 0));
      
      setModelGroups(processedGroups);
      return processedGroups;
    } catch (error) {
      console.error('Failed to fetch model groups:', error);
      return [];
    }
  };

  // Update model counts in groups - keep API count value, update models array
  const updateGroupCounts = (models: Model[], groups: ModelGroup[]) => {
    const updatedGroups = groups.map(group => ({
      ...group,
      models: models.filter(model => model.model_type === String(group.id))
    }));
    
    setModelGroups(updatedGroups);
    return updatedGroups;
  };

  const fetchModelsData = async (type: string, targetGroupId: string = 'all', targetCategory: string = 'all') => {
    const requestId = `${type}-${Date.now()}-${Math.random()}`;
    currentRequestId.current = requestId;
    
    setLoading(true);
    try {
      const providerType = getProviderType(type);
      
      // Parallel fetch of models and groups data
      const [modelsData, groupsData] = await Promise.all([
        fetchModels(type),
        fetchModelGroupsData(providerType)
      ]);
      
      if (currentRequestId.current !== requestId) {
        return;
      }
      
      const mappedData = Array.isArray(modelsData)
        ? modelsData.map((model) => ({ ...model, id: Number(model.id) }))
        : [];
      
      setModels(mappedData);
      
      updateGroupCounts(mappedData, groupsData);
      
      // Filter models using parameters to avoid async state issues
      filterModelsByGroup(mappedData, targetGroupId, targetCategory);
      
    } catch (error) {
      console.error('Failed to fetch models data:', error);
      if (currentRequestId.current === requestId) {
        message.error(t('common.fetchFailed'));
      }
    } finally {
      if (currentRequestId.current === requestId) {
        setLoading(false);
      }
    }
  };

  const filterModelsByGroup = (allModels: Model[], groupId: string, categoryFilter?: string) => {
    let filteredByGroup = allModels;
    
    if (groupId !== 'all') {
      filteredByGroup = allModels.filter(model => 
        String(model.model_type) === groupId
      );
    }
    
    // Filter by category (only for llm_model)
    const currentTab = tabConfig.find((tab) => tab.key === activeTab);
    const category = categoryFilter !== undefined ? categoryFilter : selectedCategory;
    if (currentTab?.type === 'llm_model' && category !== 'all') {
      filteredByGroup = filteredByGroup.filter(model => {
        const modelLabel = model.label;
        if (!modelLabel) return false;
        
        if (modelLabel === category) return true;
        
        const categoryOption = MODEL_CATEGORY_OPTIONS.find(option => option.value === category);
        if (categoryOption && modelLabel === categoryOption.label) return true;
        
        return false;
      });
    }
    
    setFilteredModels(filteredByGroup);
  };

  useEffect(() => {
    fetchModelsData('llm_model');
  }, []);

  const handleSegmentedChange = (key: string) => {
    setModels([]);
    setFilteredModels([]);
    setSelectedGroupId('all');
    setSelectedCategory('all');
    setActiveTab(key);
    
    const tab = tabConfig.find((t) => t.key === key);
    if (tab) {
      fetchModelsData(tab.type, 'all', 'all');
    }
  };

  const handleSearch = (value: string) => {
    const term = value.toLowerCase();
    if (term === '') {
      filterModelsByGroup(models, selectedGroupId);
    } else {
      let currentModels = models;
      
      if (selectedGroupId !== 'all') {
        currentModels = currentModels.filter(model => 
          String(model.model_type) === selectedGroupId
        );
      }
      
      // Filter by category (only for llm_model)
      const currentTab = tabConfig.find((tab) => tab.key === activeTab);
      if (currentTab?.type === 'llm_model' && selectedCategory !== 'all') {
        currentModels = currentModels.filter(model => model.label === selectedCategory);
      }
      
      setFilteredModels(
        currentModels.filter((model) =>
          model.name?.toLowerCase().includes(term)
        )
      );
    }
  };

  const handleGroupSelect = (groupId: string) => {
    setSelectedGroupId(groupId);
    filterModelsByGroup(models, groupId);
  };

  const handleCategoryChange = (category: string) => {
    setSelectedCategory(category);
    filterModelsByGroup(models, selectedGroupId, category);
  };

  const handleGroupAdd = () => {
    setGroupModalMode('add');
    setEditingGroup(null);
    setIsGroupModalVisible(true);
  };

  const handleGroupEdit = (group: ModelGroup) => {
    setGroupModalMode('edit');
    setEditingGroup(group);
    setIsGroupModalVisible(true);
  };

  const handleGroupDelete = async (groupId: number) => {
    try {
      await deleteModelGroup('', String(groupId));
      message.success(t('common.delSuccess'));
      // Re-fetch group data with current provider_type
      const currentTab = tabConfig.find((tab) => tab.key === activeTab);
      const providerType = currentTab ? getProviderType(currentTab.type) : undefined;
      const updatedGroups = await fetchModelGroupsData(providerType);
      updateGroupCounts(models, updatedGroups);
      
      // Switch to "all" if deleting currently selected group
      if (selectedGroupId === String(groupId)) {
        setSelectedGroupId('all');
        filterModelsByGroup(models, 'all');
      }
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  const handleGroupOrderChange = async (updateData: { id: number; index: number }[]) => {
    try {
      // API only needs single group id and index
      if (updateData.length > 0) {
        const { id, index } = updateData[0];
        await updateGroupOrder('', { id, index });
        
        // Re-fetch group data to ensure sync with current provider_type
        const currentTab = tabConfig.find((tab) => tab.key === activeTab);
        const providerType = currentTab ? getProviderType(currentTab.type) : undefined;
        const updatedGroups = await fetchModelGroupsData(providerType);
        updateGroupCounts(models, updatedGroups);
        message.success(t('provider.group.reorderSuccess'));
      }
    } catch {
      message.error(t('provider.group.reorderFailed'));
    }
  };

  const handleGroupModalOk = async (values: { name: string; display_name: string; tags?: string[]; icon?: string }) => {
    setGroupModalLoading(true);
    try {
      if (groupModalMode === 'add') {
        await createModelGroup('', {
          name: values.name,
          display_name: values.display_name,
          tags: values.tags || [],
          icon: ''
        });
        message.success(t('common.addSuccess'));
      } else if (editingGroup) {
        await updateModelGroup('', String(editingGroup.id), {
          name: values.name,
          display_name: values.display_name,
          tags: values.tags || [],
          icon: ''
        });
        message.success(t('common.updateSuccess'));
      }
      
      // Re-fetch group data with current provider_type
      const currentTab = tabConfig.find((tab) => tab.key === activeTab);
      const providerType = currentTab ? getProviderType(currentTab.type) : undefined;
      const updatedGroups = await fetchModelGroupsData(providerType);
      updateGroupCounts(models, updatedGroups);
      setIsGroupModalVisible(false);
    } catch {
      message.error(groupModalMode === 'add' ? t('common.addFailed') : t('common.updateFailed'));
    } finally {
      setGroupModalLoading(false);
    }
  };
  
  const handleAddProvider = async (values: any) => {
    const type = tabConfig.find((tab) => tab.key === activeTab)?.type || '';
    const configField = CONFIG_MAP[type];

    const payload: any = {
      name: values.name,
      enabled: values.enabled,
      team: values.team,
      label: values.label,
      model_type: values.model_type,
    };

    // Build payload based on provider type
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
      await addProvider(type, payload);
      message.success(t('common.saveSuccess'));
      fetchModelsData(type);
      setIsAddModalVisible(false);
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const getCurrentGroupName = () => {
    if (selectedGroupId === 'all') {
      return t('common.all');
    }
    const group = modelGroups.find(g => String(g.id) === selectedGroupId);
    return group?.display_name || group?.name || '';
  };

  // Create a refresh function that refetches both models and groups data
  const refreshData = async () => {
    const currentTab = tabConfig.find((tab) => tab.key === activeTab);
    if (currentTab) {
      await fetchModelsData(currentTab.type, selectedGroupId, selectedCategory);
    }
  };

  return (
    <div className={`w-full h-full ${styles.segmented}`}>
      <Segmented
        options={tabConfig.map((tab) => ({label: tab.label, value: tab.key}))}
        value={activeTab}
        onChange={handleSegmentedChange}
        className="mb-4"
      />
      
      <div className="flex gap-4" style={{ height: 'calc(100% - 55px)' }}>
        {/* Left sidebar - Model groups tree */}
        <div className="w-60 h-full flex-shrink-0 overflow-auto">
          <ModelTree
            filterType={tabConfig.find((tab) => tab.key === activeTab)?.type || ''}
            groups={modelGroups}
            selectedGroupId={selectedGroupId}
            onGroupSelect={handleGroupSelect}
            onGroupAdd={handleGroupAdd}
            onGroupEdit={handleGroupEdit}
            onGroupDelete={handleGroupDelete}
            onGroupOrderChange={handleGroupOrderChange}
            loading={loading}
          />
        </div>
        
        {/* Right content area */}
        <div className="flex-1 flex flex-col min-w-0 bg-[var(--color-bg-1)] rounded-md p-4 h-full overflow-auto">
          <div className="flex justify-between items-center mb-4">
            <h2 className="font-semibold">{getCurrentGroupName()}</h2>
            <div className="flex items-center gap-2">
              {/* Category filter for LLM models only */}
              {tabConfig.find((tab) => tab.key === activeTab)?.type === 'llm_model' && (
                <Select
                  value={selectedCategory}
                  onChange={handleCategoryChange}
                  placeholder={t('provider.form.label')}
                  className="w-32"
                  size="middle"
                >
                  <Select.Option value="all">{t('common.all')}</Select.Option>
                  {MODEL_CATEGORY_OPTIONS.map((option) => (
                    <Select.Option key={option.value} value={option.value}>
                      {option.label}
                    </Select.Option>
                  ))}
                </Select>
              )}
              <Search
                allowClear
                enterButton
                placeholder={`${t('common.search')}...`}
                className="w-60"
                onSearch={handleSearch}
              />
              {activeTab !== '4' && (
                <Button type="primary" onClick={() => setIsAddModalVisible(true)}>
                  {t('common.add')}
                </Button>
              )}
            </div>
          </div>
          
          <div className="flex-1 overflow-auto pt-1">
            {loading ? (
              <ProviderGridSkeleton />
            ) : (
              <ProviderGrid
                models={filteredModels}
                filterType={tabConfig.find((tab) => tab.key === activeTab)?.type || ''}
                loading={loading}
                setModels={(updatedModels) => {
                  if (typeof updatedModels === 'function') {
                    const newModels = updatedModels(models);
                    setModels(newModels);
                    filterModelsByGroup(newModels, selectedGroupId);
                  } else {
                    setModels(updatedModels);
                    filterModelsByGroup(updatedModels, selectedGroupId);
                  }
                }}
                onRefreshData={refreshData}
              />
            )}
          </div>
        </div>
      </div>
      
      {/* Add/Edit model modal */}
      <ConfigModal
        visible={isAddModalVisible}
        mode="add"
        filterType={tabConfig.find((tab) => tab.key === activeTab)?.type || ''}
        confirmLoading={modalLoading}
        onOk={handleAddProvider}
        onCancel={() => setIsAddModalVisible(false)}
      />
      
      {/* Add/Edit group modal */}
      <ModelGroupModal
        visible={isGroupModalVisible}
        mode={groupModalMode}
        group={editingGroup}
        onOk={handleGroupModalOk}
        onCancel={() => setIsGroupModalVisible(false)}
        confirmLoading={groupModalLoading}
      />
    </div>
  );
};

export default ProviderPage;
