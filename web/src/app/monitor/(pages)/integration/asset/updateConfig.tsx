import { ModalRef, ModalProps, TableDataItem } from '@/app/monitor/types';
import { Form, Button, message, Spin, Alert } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { cloneDeep } from 'lodash';
import React, {
  useState,
  useRef,
  useMemo,
  useImperativeHandle,
  useEffect,
  forwardRef,
} from 'react';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import useApiClient from '@/utils/request';
import { usePluginFromJson } from '@/app/monitor/hooks/integration/usePluginFromJson';
import { cloudRegionProviderFromPlugin, cloudRegionProviderHintsFromRow, resolveStoredCollectConfigId, useCloudRegionOptions } from '@/app/monitor/hooks/integration/useQcloudRegionOptions';
import {
  getSnmpFilterMutexConflicts,
  trackSnmpFilterMutexLastChanged
} from '@/app/monitor/hooks/integration/snmpFilterMutex';
import { getSnmpInterfaceFilterModePatch } from '@/app/monitor/hooks/integration/snmpInterfaceFilterMode';
import { getIfmibSnapshotEnabled } from '../list/detail/configure/ifmibDeploymentState';
import { normalizePasswordFields } from '@/components/password/normalizePasswordWhitespace';

interface PluginFormField {
  name?: string;
  type?: string;
  editable?: boolean;
  default_value?: unknown;
  options_key?: string;
}

interface PluginConfig {
  form_fields?: PluginFormField[];
  instance_type?: string;
  config_type?: string[];
  object_name?: string;
  name?: string;
}

const UpdateConfig = forwardRef<ModalRef, ModalProps>(({ onSuccess }, ref) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const { post } = useApiClient();
  const jsonConfig = usePluginFromJson();
  const formRef = useRef(null);
  const [pluginId, setPluginId] = useState<string | number>('');
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [modalVisible, setModalVisible] = useState<boolean>(false);
  const [title, setTitle] = useState<string>('');
  const [configForm, setConfigForm] = useState<TableDataItem>({});
  const [currentConfig, setCurrentConfig] = useState<PluginConfig | null>(null);
  const [configLoading, setConfigLoading] = useState<boolean>(false);
  const [regionHints, setRegionHints] = useState<{
    objectName?: string;
    pluginName?: string;
  }>({});
  const [collectConfigId, setCollectConfigId] = useState<
    string | string[] | undefined
  >();
  const editFormSeedKeyRef = useRef('');

  useImperativeHandle(ref, () => ({
    showModal: async ({ form, title }) => {
      const _form = cloneDeep(form);
      setTitle(title);
      setModalVisible(true);
      setConfirmLoading(false);
      setConfigForm(_form.config_content || {});
      setCollectConfigId(
        resolveStoredCollectConfigId(_form) ??
          resolveStoredCollectConfigId(_form.config_content)
      );
      const collector = _form.collector;
      const collect_type = _form.collect_type;
      const monitor_object_id = _form.monitor_object_id;
      setRegionHints(cloudRegionProviderHintsFromRow(_form as Record<string, unknown>));
      const _pluginId = _form.monitor_plugin_id || `${monitor_object_id}_${collector}_${collect_type}`;
      setPluginId(_pluginId);
      setConfigLoading(true);
      try {
        const config = await jsonConfig.getPluginConfig(
          {
            collector,
            collect_type,
            monitor_object_id,
            monitor_plugin_id: _form.monitor_plugin_id,
          },
          'edit'
        );
        setCurrentConfig(config);
      } finally {
        setConfigLoading(false);
      }
    },
  }));

  // 获取配置信息
  const regionProvider = cloudRegionProviderFromPlugin(currentConfig, regionHints);
  const resolvedCollectConfigId =
    collectConfigId ??
    resolveStoredCollectConfigId({
      config_content: configForm,
      child: (configForm as { child?: { id?: unknown } })?.child,
    });
  const {
    regionOptions,
    loadingRegions,
    refreshRegions,
    multiple: regionMultiple,
  } = useCloudRegionOptions({
    enabled: Boolean(regionProvider && modalVisible),
    provider: regionProvider || 'qcloud',
    form,
    credentialSource: 'stored',
    collectConfigId: resolvedCollectConfigId,
  });

  const configsInfo = useMemo(() => {
    if (configLoading || !currentConfig || !pluginId) {
      return {
        formItems: null,
        getDefaultForm: () => ({}),
        getParams: () => ({}),
      };
    }
    return jsonConfig.buildPluginUI(pluginId, {
      mode: 'edit',
      form,
      externalOptions: {
        region_option: regionOptions,
      },
      optionControls: {
        region_option: {
          loading: loadingRegions,
          onRefresh: refreshRegions,
          multiple: regionMultiple,
          refreshTip: t(
            'monitor.integrations.refreshStoredCloudRegionsTip',
            '刷新可用地域'
          ),
        },
      },
    });
  }, [
    configLoading,
    currentConfig,
    pluginId,
    form,
    regionOptions,
    loadingRegions,
    refreshRegions,
    regionMultiple,
    jsonConfig.buildPluginUI,
    t,
  ]);

  const formItems = useMemo(() => {
    return configsInfo.formItems;
  }, [configsInfo]);
  const supportsIfmib = Boolean(currentConfig?.form_fields?.some((field) => field.name === 'enable_ifmib'));
  const ifmibSnapshotEnabled = getIfmibSnapshotEnabled(
    configForm as Record<string, unknown>,
    supportsIfmib,
  );

  useEffect(() => {
    if (!modalVisible) {
      editFormSeedKeyRef.current = '';
      return;
    }
    if (configLoading || !currentConfig || !pluginId || !configForm) {
      return;
    }
    const collectKey = Array.isArray(collectConfigId)
      ? collectConfigId.join(',')
      : String(collectConfigId ?? '');
    const seedKey = `${pluginId}::${collectKey}`;
    // 地域 options / loading 变化会重建 configsInfo；不得据此回填，否则刚选的地域会被冲掉。
    if (editFormSeedKeyRef.current === seedKey) {
      return;
    }
    editFormSeedKeyRef.current = seedKey;
    initData(cloneDeep(configForm));
  }, [
    modalVisible,
    configLoading,
    currentConfig,
    pluginId,
    configForm,
    collectConfigId,
  ]);

  const initData = (row: TableDataItem) => {
    const activeFormData = configsInfo.getDefaultForm?.(row) || {};
    const snapshotEnabled = getIfmibSnapshotEnabled(
      row as Record<string, unknown>,
      Boolean(currentConfig?.form_fields?.some((field) => field.name === 'enable_ifmib')),
    );
    if (snapshotEnabled !== undefined) {
      activeFormData.enable_ifmib = snapshotEnabled;
    }
    form.setFieldsValue(activeFormData);
    // 用当前值初始化互斥追踪基线，避免默认排除被误判为“后填写”
    trackSnmpFilterMutexLastChanged({}, form.getFieldsValue(true), form);
  };

  const handleCancel = () => {
    form.resetFields();
    setModalVisible(false);
    setPluginId('');
    setCurrentConfig(null);
    setCollectConfigId(undefined);
  };

  const handleSubmit = () => {
    const touchedPasswordFields = (currentConfig?.form_fields || []).filter(
      (field) =>
        field.type === 'password' &&
        field.editable !== false &&
        typeof field.name === 'string' &&
        form.isFieldTouched(field.name)
    );
    const normalizedForm = normalizePasswordFields(
      form.getFieldsValue(true),
      touchedPasswordFields
    );
    if (normalizedForm.changedFields.length) {
      form.setFieldsValue(normalizedForm.values);
      message.warning(t('common.passwordWhitespaceTrimmed'));
    }
    form.validateFields().then((values) => {
      const mutexErrors = getSnmpFilterMutexConflicts(values, t);
      if (mutexErrors.length) {
        mutexErrors.forEach((msg) => message.error(msg));
        return;
      }
      operateConfig(values);
    });
  };

  const operateConfig = async (params: TableDataItem) => {
    try {
      setConfirmLoading(true);
      const data = configsInfo.getParams?.(params, configForm) || {};
      await post(
        '/monitor/api/node_mgmt/update_instance_collect_config/',
        data
      );
      message.success(t('common.successfullyModified'));
      handleCancel();
      onSuccess();
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : '';
      message.error(errorMessage || t('common.operationFailed'));
    } finally {
      setConfirmLoading(false);
    }
  };

  // 判断是否显示空状态
  const showEmpty = !configLoading && !formItems?.props?.children?.length;

  return (
    <OperateModal
      width={700}
      title={title}
      visible={modalVisible}
      zIndex={2000}
      styles={{
        body: { overflow: 'visible', maxHeight: 'calc(80vh - 108px)' },
      }}
      onCancel={handleCancel}
      footer={
        <div>
          <Button
            className="mr-[10px]"
            type="primary"
            loading={confirmLoading}
            disabled={configLoading || showEmpty}
            onClick={handleSubmit}
          >
            {t('common.confirm')}
          </Button>
          <Button onClick={handleCancel}>{t('common.cancel')}</Button>
        </div>
      }
    >
      <div className="px-[10px]">
        <Spin spinning={configLoading} className="w-full">
          <div style={{ minHeight: configLoading ? '200px' : 'auto' }}>
            {ifmibSnapshotEnabled !== undefined && (
              <Alert
                className="mb-3"
                type={ifmibSnapshotEnabled ? 'info' : 'warning'}
                showIcon
                message={t(ifmibSnapshotEnabled
                  ? 'monitor.integrations.ifmibSnapshotEnabled'
                  : 'monitor.integrations.ifmibSnapshotDisabled')}
                description={t('monitor.integrations.ifmibSnapshotDescription')}
              />
            )}
            {showEmpty ? (
              <CompactEmptyState description={t('monitor.integrations.noConfigData')} />
            ) : (
              <Form
                ref={formRef}
                form={form}
                name="basic"
                layout="vertical"
                onValuesChange={(changed, all) => {
                  const defaultIfTypeExclude = currentConfig?.form_fields?.find(
                    (field) => field.name === 'iftype_exclude'
                  )?.default_value;
                  const interfaceFilterModePatch = getSnmpInterfaceFilterModePatch(
                    changed,
                    defaultIfTypeExclude
                  );
                  const nextValues = Object.keys(interfaceFilterModePatch).length
                    ? { ...all, ...interfaceFilterModePatch }
                    : all;
                  if (Object.keys(interfaceFilterModePatch).length) {
                    form.setFieldsValue(interfaceFilterModePatch);
                  }
                  trackSnmpFilterMutexLastChanged(changed, nextValues, form);
                }}
              >
                {formItems}
              </Form>
            )}
          </div>
        </Spin>
      </div>
    </OperateModal>
  );
});

UpdateConfig.displayName = 'UpdateConfig';

export default UpdateConfig;
