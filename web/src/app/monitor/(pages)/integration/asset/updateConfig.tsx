import { ModalRef, ModalProps, TableDataItem } from '@/app/monitor/types';
import { Form, Button, message, InputNumber, Select, Spin } from 'antd';
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
import useIntegrationApi from '@/app/monitor/api/integration';
import { useMonitorConfig } from '@/app/monitor/hooks/integration/index';
import { TIMEOUT_UNITS } from '@/app/monitor/constants/integration';
const { Option } = Select;

const UpdateConfig = forwardRef<ModalRef, ModalProps>(({ onSuccess }, ref) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const { post } = useApiClient();
  const { getConfigContent } = useIntegrationApi();
  const configs = useMonitorConfig();
  const formRef = useRef(null);
  const [pluginName, setPluginName] = useState<string>('');
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [modalVisible, setModalVisible] = useState<boolean>(false);
  const [title, setTitle] = useState<string>('');
  const [configForm, setConfigForm] = useState<TableDataItem>({});
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [objectName, setObjectName] = useState<string>('');

  useImperativeHandle(ref, () => ({
    showModal: ({ form, title }) => {
      const _form = cloneDeep(form);
      setTitle(title);
      setModalVisible(true);
      setConfirmLoading(false);
      getContent(_form);
    },
  }));

  const getContent = async (data: any) => {
    setPageLoading(true);
    try {
      const res = await getConfigContent({
        ids: data.config_ids,
      });
      setConfigForm(res);
      const plugins = configs.config[data.objName].plugins || {};
      const _PluginName = Object.keys(plugins).find((key) => {
        const pluginItem = plugins[key]?.getPluginCfg({ mode: 'edit' });
        return (
          pluginItem?.collect_type === data.collect_type &&
          (pluginItem?.config_type || []).includes(data.config_type)
        );
      });
      setPluginName(_PluginName as string);
      setObjectName(data.objName);
    } finally {
      setPageLoading(false);
    }
  };

  const configsInfo = useMemo(() => {
    return configs.getPlugin({
      objectName,
      mode: 'edit',
      pluginName,
    });
  }, [pluginName, objectName]);

  const formItems = useMemo(() => {
    return configsInfo.formItems;
  }, [configsInfo]);

  useEffect(() => {
    if (configsInfo?.getDefaultForm && configForm) {
      initData(cloneDeep(configForm));
    }
  }, [configsInfo, configForm]);

  const initData = (row: TableDataItem) => {
    const formData: Record<string, any> = cloneDeep(
      row?.child?.content?.config || {}
    );
    if (formData.interval) {
      formData.interval = +formData.interval.replace('s', '');
    }
    if (formData.timeout) {
      formData.timeout = +formData.timeout.replace('s', '');
    }
    const activeFormData = configsInfo.getDefaultForm(row);
    form.setFieldsValue({
      ...formData,
      ...activeFormData,
    });
  };

  const handleCancel = () => {
    form.resetFields();
    setModalVisible(false);
    setPageLoading(false);
  };

  const handleSubmit = () => {
    form.validateFields().then((values) => {
      operateConfig(values);
    });
  };

  const operateConfig = async (params: TableDataItem) => {
    const data = configsInfo.getParams(params, configForm);
    if (params.timeout) {
      data.child.content.config.timeout = params.timeout + 's';
    }
    data.child.content.config.interval = params.interval + 's';
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

  return (
    <OperateModal
      width={700}
      title={title}
      visible={modalVisible}
      onCancel={handleCancel}
      footer={
        <div>
          <Button
            className="mr-[10px]"
            type="primary"
            loading={confirmLoading}
            disabled={pageLoading}
            onClick={handleSubmit}
          >
            {t('common.confirm')}
          </Button>
          <Button onClick={handleCancel}>{t('common.cancel')}</Button>
        </div>
      }
    >
      <Spin spinning={pageLoading}>
        <div className="px-[10px]">
          <Form ref={formRef} form={form} name="basic" layout="vertical">
            {formItems}
            <Form.Item required label={t('monitor.integrations.interval')}>
              <Form.Item
                noStyle
                name="interval"
                rules={[
                  {
                    required: true,
                    message: t('common.required'),
                  },
                ]}
              >
                <InputNumber
                  className="mr-[10px]"
                  min={1}
                  precision={0}
                  addonAfter={
                    <Select style={{ width: 116 }} defaultValue="s">
                      {TIMEOUT_UNITS.map((item: string) => (
                        <Option key={item} value={item}>
                          {item}
                        </Option>
                      ))}
                    </Select>
                  }
                />
              </Form.Item>
              <span className="text-[12px] text-[var(--color-text-3)]">
                {t('monitor.integrations.intervalDes')}
              </span>
            </Form.Item>
          </Form>
        </div>
      </Spin>
    </OperateModal>
  );
});

UpdateConfig.displayName = 'UpdateConfig';

export default UpdateConfig;
