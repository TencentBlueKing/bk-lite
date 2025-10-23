import React, { useState, useMemo } from 'react';
import { Spin, message, Dropdown, Menu, Modal, Empty, Divider } from 'antd';
import Image from 'next/image';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';
import comStyles from '@/app/opspilot/styles/common.module.scss';
import { Model, ModelConfig } from '@/app/opspilot/types/provider';
import PermissionWrapper from '@/components/permission';
import ConfigModal from '@/app/opspilot/components/provider/configModal';
import { useProviderApi } from '@/app/opspilot/api/provider';
import { CONFIG_MAP, MODEL_CATEGORY_MAPPING } from '@/app/opspilot/constants/provider';

interface ProviderGridProps {
  models: Model[];
  filterType: string;
  loading: boolean;
  setModels: React.Dispatch<React.SetStateAction<Model[]>>;
  onRefreshData?: () => void;
}

const ProviderGrid: React.FC<ProviderGridProps> = ({ models, filterType, loading, setModels, onRefreshData }) => {
  const { t } = useTranslation();
  const { updateProvider, deleteProvider } = useProviderApi();
  const [isModalVisible, setIsModalVisible] = useState<boolean>(false);
  const [modalLoading, setModalLoading] = useState<boolean>(false);
  const [selectedModel, setSelectedModel] = useState<Model | null>(null);

  const getModelIconPath = (model: Model) => {
    const iconName = model.icon || 'Default';
    return `/app/models/${iconName}.svg`;
  };

  const handleMenuClick = (action: string, model: Model) => {
    if (action === 'edit') {
      setSelectedModel(model);
      setIsModalVisible(true);
    } else if (action === 'delete') {
      handleDelete(model);
    }
  };

  const menu = (model: Model) => (
    <Menu className={`${comStyles.menuContainer}`}>
      <Menu.Item key="edit">
        <PermissionWrapper 
          className='w-full' 
          requiredPermissions={['Setting']}
          instPermissions={model.permissions || []}>
          <span className='block w-full' onClick={() => handleMenuClick('edit', model)}>{t('common.edit')}</span>
        </PermissionWrapper>
      </Menu.Item>
      {model.is_build_in === false && (<Menu.Item key="delete">
        <PermissionWrapper 
          className='w-full' 
          requiredPermissions={['Delete']}
          instPermissions={model.permissions || []}>
          <span className='block w-full' onClick={() => handleMenuClick('delete', model)}>{t('common.delete')}</span>
        </PermissionWrapper>
      </Menu.Item>)}
    </Menu>
  );

  const handleEditOk = async (values: any) => {
    if (!selectedModel) return;

    const configField = CONFIG_MAP[filterType];
    const updatedModel: Model = {
      ...selectedModel,
      name: values.name,
      label: values.label,
      model_type: values.model_type,
      enabled: values.enabled,
      team: values.team
    };

    // Build different config based on provider type
    if (filterType === 'llm_model') {
      updatedModel.llm_config = {
        ...selectedModel.llm_config,
        model: values.modelName,
        openai_api_key: values.apiKey,
        openai_base_url: values.url,
      };
    } else {
      if (!configField) {
        throw new Error(`Invalid filterType: ${filterType}`);
      }
      (updatedModel[configField as keyof Model] as ModelConfig) = {
        ...(selectedModel[configField as keyof Model] as ModelConfig),
        base_url: values.url,
        api_key: values.apiKey,
        ...(filterType !== 'ocr_provider' && { model: values.modelName })
      };
    }

    setModalLoading(true);
    try {
      const result = await updateProvider(filterType, selectedModel.id, updatedModel);
      if (result && result.id) {
        message.success(t('common.updateSuccess'));
        setModels(prevModels => prevModels.map(model => (model.id === updatedModel.id ? updatedModel : model)));
        setIsModalVisible(false);
        onRefreshData && onRefreshData();
      } else {
        message.error(t('common.updateFailed'));
      }
    } catch {
      message.error(t('common.updateFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const handleDelete = async (model: Model) => {
    Modal.confirm({
      title: `${t('provider.deleteConfirm')}`,
      onOk: async () => {
        try {
          await deleteProvider(filterType, model.id);
          message.success(t('common.delSuccess'));
          setModels(prevModels => prevModels.filter(item => item.id !== model.id));
          onRefreshData && onRefreshData();
        } catch {
          message.error(t('common.delFailed'));
        }
      },
    });
  };

  // 将模型按照启用状态分组
  const { enabledModels, disabledModels } = useMemo(() => {
    const enabled = models.filter(model => model.enabled);
    const disabled = models.filter(model => !model.enabled);
    return { enabledModels: enabled, disabledModels: disabled };
  }, [models]);

  const renderModelGrid = (modelList: Model[]) => (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-4">
      {modelList.map((model) => (
        <div className={`rounded-lg p-4 relative ${styles.gridContainer}`} key={model.id}>
          <div className="flex justify-between items-start">
            <div style={{flex: '0 0 auto'}}>
              <Image
                src={getModelIconPath(model)}
                alt={model.name}
                width={45}
                height={45}
                className="object-contain"
              />
            </div>
            <div className={`flex-1 ml-2 ${styles.nameContainer}`}>
              <h3 className={`text-sm font-semibold break-words mb-1 ${styles.name}`}>{model.name}</h3>
              <div className="flex flex-wrap gap-1 mt-1">
                {model.model_type_name && (
                  <span className="inline-block font-mini px-2 py-0.2 rounded-sm bg-blue-50 text-blue-600">
                    {model.model_type_name}
                  </span>
                )}
                {model.label && (
                  <span className="inline-block font-mini px-2 py-0.2 rounded-sm bg-green-50 text-green-600">
                    {MODEL_CATEGORY_MAPPING[model.label] || model.label}
                  </span>
                )}
              </div>
            </div>
            <Dropdown overlay={menu(model)} trigger={['click']} placement="bottomRight">
              <div className="cursor-pointer">
                <Icon type="sangedian-copy" className="text-xl" />
              </div>
            </Dropdown>
          </div>
          <div className="absolute bottom-0 right-0 rounded-lg z-20">
            <span className={`${styles.iconTriangle} ${model.enabled ? styles.enabled : styles.disabled}`}>
              {model.enabled ? <Icon type="select-line" /> : <Icon type="guanbi" />}
            </span>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <>
      <Spin spinning={loading}>
        {!loading && models.length === 0 ? (
          <Empty description={t('common.noData')} />
        ) : (
          <div className="space-y-6">
            {enabledModels.length > 0 && (
              <div>
                {renderModelGrid(enabledModels)}
              </div>
            )}

            {enabledModels.length > 0 && disabledModels.length > 0 && (
              <Divider className="my-6" />
            )}

            {disabledModels.length > 0 && (
              <div>
                {renderModelGrid(disabledModels)}
              </div>
            )}
          </div>
        )}
      </Spin>
      <ConfigModal
        visible={isModalVisible}
        mode="edit"
        filterType={filterType}
        model={selectedModel}
        confirmLoading={modalLoading}
        onOk={handleEditOk}
        onCancel={() => setIsModalVisible(false)}
      />
    </>
  );
};

export default ProviderGrid;
