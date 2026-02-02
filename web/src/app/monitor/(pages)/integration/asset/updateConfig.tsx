import { ModalRef, ModalProps, TableDataItem } from '@/app/monitor/types';
import { Form, Button, message, Spin, Empty } from 'antd';
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
  const [currentConfig, setCurrentConfig] = useState<any>(null);
  const [configLoading, setConfigLoading] = useState<boolean>(false);

  useImperativeHandle(ref, () => ({
    showModal: async ({ form, title }) => {
      const _form = cloneDeep(form);
      setTitle(title);
      setModalVisible(true);
      setConfirmLoading(false);
      setConfigForm(_form.config_content || {});
      const collector = _form.collector;
      const collect_type = _form.collect_type;
      const monitor_object_id = _form.monitor_object_id;
      const _pluginId = `${monitor_object_id}_${collector}_${collect_type}`;
      setPluginId(_pluginId);
      setConfigLoading(true);
      try {
        const config = await jsonConfig.getPluginConfig(
          {
            collector,
            collect_type,
            monitor_object_id,
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
    });
  }, [configLoading, currentConfig, pluginId, form, jsonConfig.buildPluginUI]);

  const formItems = useMemo(() => {
    return configsInfo.formItems;
  }, [configsInfo]);

  useEffect(() => {
    if (configsInfo?.getDefaultForm && configForm && !configLoading) {
      initData(cloneDeep(configForm));
    }
  }, [configsInfo, configForm, configLoading]);

  const initData = (row: TableDataItem) => {
    const activeFormData = configsInfo.getDefaultForm?.(row) || {};
    form.setFieldsValue(activeFormData);
  };

  const handleCancel = () => {
    form.resetFields();
    setModalVisible(false);
    setPluginId('');
    setCurrentConfig(null);
  };

  const handleSubmit = () => {
    form.validateFields().then((values) => {
      operateConfig(values);
    });
  };

  const operateConfig = async (params: TableDataItem) => {
    const data = configsInfo.getParams?.(params, configForm) || {};
    try {
      setConfirmLoading(true);
      await post(
        '/monitor/api/node_mgmt/update_instance_collect_config/',
        data
      );
      message.success(t('common.successfullyModified'));
      handleCancel();
      onSuccess();
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
            {showEmpty ? (
              <Empty description={t('monitor.integrations.noConfigData')} />
            ) : (
              <Form ref={formRef} form={form} name="basic" layout="vertical">
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
