'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Empty, Input, Popconfirm, Spin, Switch, message } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useProviderApi } from '@/app/opspilot/api/provider';
import ModelItemModal from '@/app/opspilot/components/provider/modelItemModal';
import { CONFIG_MAP, MODEL_TABS } from '@/app/opspilot/constants/provider';
import type { Model, ModelVendor, ProviderResourceType } from '@/app/opspilot/types/provider';
import { useTranslation } from '@/utils/i18n';

const { Search } = Input;

interface ProviderModelManagementProps {
  vendorId: number;
}

type ModelSectionState = Record<ProviderResourceType, Model[]>;

const SECTION_TITLE_MAP: Record<ProviderResourceType, string> = {
  llm_model: 'LLM模型',
  embed_provider: '向量模型',
  rerank_provider: '重排模型',
  ocr_provider: '图像模型',
};

const SECTION_STYLE_MAP: Record<ProviderResourceType, { topGlow: string; panelGlow: string; headerBg: string }> = {
  llm_model: {
    topGlow: 'linear-gradient(180deg, rgba(231, 240, 253, 0.62) 0%, rgba(244, 249, 255, 0.38) 42%, rgba(255, 255, 255, 0) 100%)',
    panelGlow: 'rgba(147, 197, 253, 0.14)',
    headerBg: 'linear-gradient(135deg, rgba(249, 252, 255, 1) 0%, rgba(238, 246, 255, 0.94) 100%)',
  },
  embed_provider: {
    topGlow: 'linear-gradient(180deg, rgba(231, 240, 253, 0.62) 0%, rgba(244, 249, 255, 0.38) 42%, rgba(255, 255, 255, 0) 100%)',
    panelGlow: 'rgba(147, 197, 253, 0.14)',
    headerBg: 'linear-gradient(135deg, rgba(249, 252, 255, 1) 0%, rgba(238, 246, 255, 0.94) 100%)',
  },
  rerank_provider: {
    topGlow: 'linear-gradient(180deg, rgba(231, 240, 253, 0.62) 0%, rgba(244, 249, 255, 0.38) 42%, rgba(255, 255, 255, 0) 100%)',
    panelGlow: 'rgba(147, 197, 253, 0.14)',
    headerBg: 'linear-gradient(135deg, rgba(249, 252, 255, 1) 0%, rgba(238, 246, 255, 0.94) 100%)',
  },
  ocr_provider: {
    topGlow: 'linear-gradient(180deg, rgba(231, 240, 253, 0.62) 0%, rgba(244, 249, 255, 0.38) 42%, rgba(255, 255, 255, 0) 100%)',
    panelGlow: 'rgba(147, 197, 253, 0.14)',
    headerBg: 'linear-gradient(135deg, rgba(249, 252, 255, 1) 0%, rgba(238, 246, 255, 0.94) 100%)',
  },
};

const EMPTY_MODELS: ModelSectionState = {
  llm_model: [],
  embed_provider: [],
  rerank_provider: [],
  ocr_provider: [],
};

const ProviderModelManagement: React.FC<ProviderModelManagementProps> = ({ vendorId }) => {
  const { t } = useTranslation();
  const { fetchModels, fetchModelDetail, addProvider, updateProvider, deleteProvider, fetchVendorDetail } = useProviderApi();
  const [loading, setLoading] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const [modelsByType, setModelsByType] = useState<ModelSectionState>(EMPTY_MODELS);
  const [vendorDetail, setVendorDetail] = useState<ModelVendor | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalType, setModalType] = useState<ProviderResourceType>('llm_model');
  const [editingModel, setEditingModel] = useState<Model | null>(null);
  const [switchingKey, setSwitchingKey] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [vendor, ...responses] = await Promise.all([
        fetchVendorDetail(vendorId),
        ...MODEL_TABS.map(({ type }) => fetchModels(type, { vendor: vendorId })),
      ]);

      setVendorDetail(vendor);
      setModelsByType({
        llm_model: Array.isArray(responses[0]) ? responses[0].map((item) => ({ ...item, id: Number(item.id) })) : [],
        embed_provider: Array.isArray(responses[1]) ? responses[1].map((item) => ({ ...item, id: Number(item.id) })) : [],
        rerank_provider: Array.isArray(responses[2]) ? responses[2].map((item) => ({ ...item, id: Number(item.id) })) : [],
        ocr_provider: Array.isArray(responses[3]) ? responses[3].map((item) => ({ ...item, id: Number(item.id) })) : [],
      });
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [vendorId]);

  const filteredModelsByType = useMemo(() => {
    const keyword = searchValue.trim().toLowerCase();
    if (!keyword) {
      return modelsByType;
    }

    return MODEL_TABS.reduce((acc, { type }) => {
      acc[type] = modelsByType[type].filter((model) => {
        const modelId = getModelIdentifier(model, type).toLowerCase();
        const modelName = (model.name || '').toLowerCase();
        return modelId.includes(keyword) || modelName.includes(keyword);
      });
      return acc;
    }, { ...EMPTY_MODELS });
  }, [modelsByType, searchValue]);

  const openAddModal = (type: ProviderResourceType) => {
    setModalType(type);
    setEditingModel(null);
    setModalVisible(true);
  };

  const openEditModal = (type: ProviderResourceType, model: Model) => {
    setModalType(type);
    setEditingModel(model);
    setModalVisible(true);
  };

  const updateLocalModel = (type: ProviderResourceType, modelId: number, updater: (current: Model) => Model) => {
    setModelsByType((prev) => ({
      ...prev,
      [type]: prev[type].map((item) => (item.id === modelId ? updater(item) : item)),
    }));
  };

  const removeLocalModel = (type: ProviderResourceType, modelId: number) => {
    setModelsByType((prev) => ({
      ...prev,
      [type]: prev[type].filter((item) => item.id !== modelId),
    }));
  };

  const handleModalSubmit = async (values: { name: string; model: string; team: number[] }) => {
    if (!vendorDetail) {
      message.error(t('common.fetchFailed'));
      return;
    }

    const payload = buildModelPayload({
      vendor: vendorDetail,
      values,
      model: editingModel,
    });

    setModalLoading(true);
    try {
      if (editingModel) {
        await updateProvider(modalType, editingModel.id, payload);
        message.success(t('common.updateSuccess'));
      } else {
        await addProvider(modalType, payload);
        message.success(t('common.addSuccess'));
      }

      setModalVisible(false);
      setEditingModel(null);
      await loadData();
    } catch {
      message.error(editingModel ? t('common.updateFailed') : t('common.addFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const handleDelete = async (type: ProviderResourceType, model: Model) => {
    try {
      await deleteProvider(type, model.id);
      removeLocalModel(type, model.id);
      message.success(t('common.delSuccess'));
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  const handleToggleEnabled = async (type: ProviderResourceType, model: Model, enabled: boolean) => {
    const switchingId = `${type}-${model.id}`;
    setSwitchingKey(switchingId);
    try {
      const modelDetail = await fetchModelDetail(type, model.id);
      await updateProvider(type, model.id, buildTogglePayload(modelDetail, enabled, vendorId));
      updateLocalModel(type, model.id, (current) => ({ ...current, enabled }));
      message.success(t('common.updateSuccess'));
    } catch {
      message.error(t('common.updateFailed'));
    } finally {
      setSwitchingKey(null);
    }
  };

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Search
          allowClear
          enterButton
          value={searchValue}
          placeholder={t('provider.model.searchPlaceholder')}
          className="w-full max-w-[320px]"
          onChange={(event) => setSearchValue(event.target.value)}
          onSearch={() => {}}
        />
        <Button icon={<ReloadOutlined />} onClick={loadData} />
      </div>

      <Spin spinning={loading} className="flex-1">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {MODEL_TABS.map(({ type }) => {
            const sectionModels = filteredModelsByType[type];
            const sectionStyle = SECTION_STYLE_MAP[type];

            return (
              <section
                key={type}
                className="relative flex flex-col overflow-hidden rounded-2xl border bg-white"
                style={{
                  borderColor: 'rgba(191, 219, 254, 0.7)',
                  background: 'linear-gradient(180deg, rgba(249, 252, 255, 0.97) 0%, rgba(255, 255, 255, 0.99) 34%, rgba(255, 255, 255, 1) 100%)',
                  boxShadow: '0 14px 28px rgba(148, 163, 184, 0.08)',
                  height: 'calc((100vh - 360px) / 2)',
                  minHeight: 240,
                }}
              >
                <div
                  className="pointer-events-none absolute inset-x-0 top-0 h-24"
                  style={{ background: sectionStyle.topGlow }}
                />
                <div
                  className="pointer-events-none absolute -top-7 left-10 h-20 w-36 rounded-full blur-3xl"
                  style={{ background: sectionStyle.panelGlow }}
                />

                <div
                  className="relative flex items-center justify-between border-b px-4 py-3"
                  style={{ borderColor: 'rgba(191, 219, 254, 0.55)', background: sectionStyle.headerBg }}
                >
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-semibold" style={{ color: 'var(--color-text-1)' }}>{SECTION_TITLE_MAP[type]}</h3>
                    <span className="text-xs" style={{ color: 'var(--color-text-3)' }}>{t('provider.model.totalCount', undefined, { count: modelsByType[type].length })}</span>
                  </div>
                  <Button type="primary" ghost size="small" icon={<PlusOutlined />} onClick={() => openAddModal(type)}>
                    {t('provider.model.add')}
                  </Button>
                </div>

                {sectionModels.length === 0 ? (
                  <div className="relative flex flex-1 items-center justify-center px-4 py-8">
                    <Empty description={t('provider.model.empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  </div>
                ) : (
                  <div className="relative flex-1 overflow-auto bg-white/82 backdrop-blur-[2px]">
                    <div className="min-w-160">
                      <div className="grid grid-cols-[1.2fr_1.4fr_1fr_88px_100px] border-b px-4 py-3 text-xs font-medium" style={{ borderColor: 'var(--color-border-2)', color: 'var(--color-text-3)' }}>
                        <span>{t('provider.model.modelName')}</span>
                        <span>{t('provider.model.modelId')}</span>
                        <span>{t('provider.model.availableGroups')}</span>
                        <span>{t('provider.model.enabled')}</span>
                        <span>{t('common.edit')}</span>
                      </div>

                      {sectionModels.map((model) => (
                        <div
                          key={`${type}-${model.id}`}
                          className="grid grid-cols-[1.2fr_1.4fr_1fr_88px_100px] items-center border-b px-4 py-3 text-sm"
                          style={{ borderColor: 'var(--color-border-2)', color: 'var(--color-text-2)' }}
                        >
                          <span className="truncate pr-3">{model.name || '--'}</span>
                          <span className="truncate pr-3">{getModelIdentifier(model, type) || '--'}</span>
                          <span className="truncate pr-3">{getTeamText(model)}</span>
                          <span>
                            <Switch
                              size="small"
                              checked={Boolean(model.enabled)}
                              loading={switchingKey === `${type}-${model.id}`}
                              disabled={switchingKey === `${type}-${model.id}`}
                              onChange={(checked) => handleToggleEnabled(type, model, checked)}
                            />
                          </span>
                          <span className="flex items-center gap-1">
                            <Button type="text" size="small" icon={<EditOutlined />} onClick={() => openEditModal(type, model)} />
                            <Popconfirm
                              title={t('provider.model.deleteConfirmTitle')}
                              okText={t('common.confirm')}
                              cancelText={t('common.cancel')}
                              okButtonProps={{ danger: true }}
                              onConfirm={() => handleDelete(type, model)}
                            >
                              <Button
                                type="text"
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                              />
                            </Popconfirm>
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </section>
            );
          })}
        </div>
      </Spin>

      <ModelItemModal
        visible={modalVisible}
        mode={editingModel ? 'edit' : 'add'}
        model={editingModel}
        confirmLoading={modalLoading}
        onOk={handleModalSubmit}
        onCancel={() => {
          setModalVisible(false);
          setEditingModel(null);
        }}
      />
    </div>
  );
};

const getTeamText = (model: Model) => {
  if (Array.isArray(model.team_name) && model.team_name.length > 0) {
    return model.team_name.join('、');
  }

  if (Array.isArray(model.team) && model.team.length > 0) {
    return model.team.join('、');
  }

  return '--';
};

const getModelIdentifier = (model: Model, type: ProviderResourceType) => {
  if (model.model) {
    return model.model;
  }

  if (type === 'llm_model') {
    return model.llm_config?.model || '';
  }

  const configField = CONFIG_MAP[type] as keyof Model;
  const config = model[configField] as Model['embed_config'];
  return config?.model || '';
};

const buildModelPayload = ({
  vendor,
  values,
  model,
}: {
  vendor: ModelVendor;
  values: { name: string; model: string; team: number[] };
  model?: Model | null;
}) => {
  const payload: Record<string, unknown> = {
    name: values.name,
    model: values.model,
    vendor: vendor.id,
    team: values.team,
    enabled: model?.enabled ?? true,
  };

  if (model?.label) {
    payload.label = model.label;
  }

  return payload;
};

const buildTogglePayload = (model: Model, enabled: boolean, vendorId: number) => {
  const payload: Record<string, unknown> = {
    ...model,
    vendor: model.vendor ?? vendorId,
    team: model.team || [],
    enabled,
  };

  delete payload.id;
  delete payload.team_name;
  delete payload.permissions;
  delete payload.vendor_name;
  delete payload.vendor_type;
  delete payload.model_type_name;
  delete payload.is_build_in;
  delete payload.group_name;
  delete payload.icon;

  return payload;
};

export default ProviderModelManagement;
