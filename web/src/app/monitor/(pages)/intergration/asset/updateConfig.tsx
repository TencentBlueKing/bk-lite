import { ModalRef, ModalProps, TableDataItem } from '@/app/monitor/types';
import { Form, Button, message, InputNumber, Select } from 'antd';
import { cloneDeep } from 'lodash';
import React, {
  useState,
  useRef,
  useImperativeHandle,
  forwardRef,
  useEffect,
} from 'react';
import { useTranslation } from '@/utils/i18n';
import { useFormItems } from '@/app/monitor/hooks/intergration';
import OperateModal from '@/components/operate-modal';
import useApiClient from '@/utils/request';
import {
  INSTANCE_TYPE_MAP,
  TIMEOUT_UNITS,
} from '@/app/monitor/constants/monitor';
const { Option } = Select;

const UpdateConfig = forwardRef<ModalRef, ModalProps>(({ onSuccess }, ref) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const { post } = useApiClient();
  const [pluginName, setPluginName] = useState<string>('');
  const [collectType, setCollectType] = useState<string>('');
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [modalVisible, setModalVisible] = useState<boolean>(false);
  const [title, setTitle] = useState<string>('');
  const [passwordDisabled, setPasswordDisabled] = useState<boolean>(true);
  const [authPasswordDisabled, setAuthPasswordDisabled] =
    useState<boolean>(true);
  const [privPasswordDisabled, setPrivPasswordDisabled] =
    useState<boolean>(true);
  const [configForm, setConfigForm] = useState<TableDataItem>({});
  const formRef = useRef(null);
  const authPasswordRef = useRef<any>(null);
  const privPasswordRef = useRef<any>(null);
  const passwordRef = useRef<any>(null);

  useImperativeHandle(ref, () => ({
    showModal: ({ form, title }) => {
      const _form = cloneDeep(form);
      const content = _form.content || {};
      setConfigForm({
        ...content,
        id: _form.config_id,
      });
      const _collectType =
        _form?.collect_type === 'http' ? 'vmware' : _form?.collect_type;
      let _PluginName =
        Object.keys(INSTANCE_TYPE_MAP).find(
          (key) =>
            INSTANCE_TYPE_MAP[key] === content.config?.tags?.instance_type
        ) || '';
      if (
        ['Hardware Server SNMP General', 'Hardware Server IPMI'].includes(
          _PluginName
        )
      ) {
        _PluginName =
          _form?.collect_type === 'ipmi'
            ? 'Hardware Server IPMI'
            : 'Hardware Server SNMP General';
      }
      if (['Storage SNMP General', 'Storage IPMI'].includes(_PluginName)) {
        _PluginName =
          _form?.collect_type === 'ipmi'
            ? 'Hardware Server IPMI'
            : 'Storage SNMP General';
      }
      setCollectType(_collectType);
      setPluginName(_PluginName);
      setTitle(title);
      setModalVisible(true);
      setConfirmLoading(false);
      initData(content.config, _PluginName);
    },
  }));

  useEffect(() => {
    if (!authPasswordDisabled && authPasswordRef?.current) {
      authPasswordRef.current.focus();
    }
  }, [authPasswordDisabled]);

  useEffect(() => {
    if (!privPasswordDisabled && privPasswordRef?.current) {
      privPasswordRef.current.focus();
    }
  }, [privPasswordDisabled]);

  useEffect(() => {
    if (!passwordDisabled && passwordRef?.current) {
      passwordRef.current.focus();
    }
  }, [passwordDisabled]);

  const handleEditAuthPassword = () => {
    if (authPasswordDisabled) {
      form.setFieldsValue({
        auth_password: '',
      });
    }
    setAuthPasswordDisabled(false);
  };

  const handleEditPrivPassword = () => {
    if (privPasswordDisabled) {
      form.setFieldsValue({
        priv_password: '',
      });
    }
    setPrivPasswordDisabled(false);
  };

  const handleEditPassword = () => {
    if (passwordDisabled) {
      form.setFieldsValue({
        password: '',
      });
    }
    setPasswordDisabled(false);
  };

  // 根据自定义hook，生成不同的模板
  const { formItems } = useFormItems({
    collectType,
    columns: [],
    authPasswordRef,
    privPasswordRef,
    passwordRef,
    authPasswordDisabled,
    privPasswordDisabled,
    passwordDisabled,
    pluginName,
    mode: 'edit',
    handleEditAuthPassword,
    handleEditPrivPassword,
    handleEditPassword,
  });

  const initData = (row: TableDataItem, name: string) => {
    const formData: Record<string, any> = cloneDeep(row);
    formData.interval = +formData.interval.replace('s', '');
    if (formData.timeout) {
      formData.timeout = +formData.timeout.replace('s', '');
    }
    if (
      [
        'Switch SNMP General',
        'Firewall SNMP General',
        'Detection Device SNMP General',
        'Loadbalance SNMP General',
        'Router SNMP General',
        'Scanning Device SNMP General',
        'Bastion Host SNMP General',
        'Storage SNMP General',
        'Hardware Server SNMP General',
      ].includes(name)
    ) {
      formData.monitor_ip =
        extractMongoDBUrl(formData.agents?.[0] || '').host || '';
      formData.port = extractMongoDBUrl(formData.agents?.[0] || '').port || '';
    }
    if (['Hardware Server IPMI', 'Storage IPMI'].includes(name)) {
      Object.assign(formData, extractIPMIUrl(formData.servers?.[0] || ''));
    }
    if (['Website', 'Ping'].includes(name)) {
      formData.monitor_url = formData.urls?.[0] || '';
    }
    switch (name) {
      case 'ElasticSearch':
        formData.server = formData.servers?.[0];
        break;
      case 'MongoDB':
        Object.assign(formData, extractMongoDBUrl(formData.servers?.[0] || ''));
        break;
      case 'Mysql':
        Object.assign(formData, extractMysqlUrl(formData.servers?.[0] || ''));
        break;
      case 'Postgres':
        Object.assign(formData, extractPostgresUrl(formData.address || ''));
        break;
      case 'Redis':
        Object.assign(formData, extractMongoDBUrl(formData.servers?.[0] || ''));
        break;
      case 'Zookeeper':
        formData.monitor_url = formData.servers?.[0] || '';
        break;
      case 'Apache':
        formData.monitor_url = formData.urls?.[0] || '';
        break;
      case 'Tomcat':
        formData.monitor_url = formData.url || '';
        break;
      case 'ClickHouse':
        formData.monitor_url = formData.servers?.[0] || '';
        break;
      case 'RabbitMQ':
        formData.monitor_url = formData.url || '';
        break;
      case 'ActiveMQ':
        formData.monitor_url = formData.url || '';
        break;
      case 'Nginx':
        formData.monitor_url = formData.urls?.[0] || '';
        break;
      case 'Consul':
        formData.monitor_url = formData.address || '';
        break;
      case 'Host':
        formData.metric_type = [formData.tags?.config_type];
        formData.monitor_ip =
          (formData.tags?.instance_id || '').split('-')?.[0] || '';
        break;
      case 'SNMP Trap':
        formData.monitor_ip =
          (formData.tags?.instance_id || '')
            .split('-')?.[0]
            ?.replace('trap', '') || '';
        break;
      case 'VMWare':
        Object.assign(formData, extractVmvareUrl(formData.urls?.[0] || ''));
        break;
      default:
        break;
    }
    form.setFieldsValue(formData);
  };

  const extractMongoDBUrl = (url: string) => {
    const regex = /\/\/([^:]+):(\d+)/;
    const matches = url.match(regex);
    if (matches && matches.length >= 3) {
      return {
        host: matches[1],
        port: matches[2],
      };
    }
    return {};
  };

  const extractMysqlUrl = (url: string) => {
    const regex = /^([^:]+):([^@]+)@tcp\(([^:]+):(\d+)\)/;
    const matches = url.match(regex);
    if (!matches || matches.length < 5) {
      return {};
    }
    return {
      username: matches[1],
      password: matches[2],
      host: matches[3],
      port: matches[4],
    };
  };

  const extractPostgresUrl = (url: string) => {
    const result = {
      host: '',
      port: '',
      username: '',
      password: '',
    };
    const regex =
      /(?:host=([^\s]+))|(?:port=([^\s]+))|(?:user=([^\s]+))|(?:password=([^\s]+))/g;
    let match;
    while ((match = regex.exec(url)) !== null) {
      if (match[1]) result.host = match[1];
      if (match[2]) result.port = match[2];
      if (match[3]) result.username = match[3];
      if (match[4]) result.password = match[4];
    }
    return result;
  };

  const extractIPMIUrl = (url: string) => {
    const regex = /([^:]+):([^@]+)@([^()]+)\(([^)]+)\)/;
    const match = url.match(regex);
    if (!match || match.length < 5) {
      return {};
    }
    return {
      monitor_ip: match[4],
      protocol: match[3],
      username: match[1],
      password: match[2],
    };
  };

  const extractVmvareUrl = (url: string) => {
    try {
      const _url = new URL(url);
      const params = new URLSearchParams(_url.search);
      return {
        host: params.get('host'),
        username: params.get('username'),
        password: params.get('password'),
      };
    } catch {
      return {};
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setModalVisible(false);
    setAuthPasswordDisabled(true);
    setPrivPasswordDisabled(true);
    setPasswordDisabled(true);
  };

  const handleSubmit = () => {
    form.validateFields().then((values) => {
      operateConfig(values);
    });
  };

  const operateConfig = async (params: TableDataItem) => {
    if (
      [
        'Switch SNMP General',
        'Firewall SNMP General',
        'Detection Device SNMP General',
        'Loadbalance SNMP General',
        'Router SNMP General',
        'Scanning Device SNMP General',
        'Bastion Host SNMP General',
        'Storage SNMP General',
        'Hardware Server SNMP General',
      ].includes(pluginName)
    ) {
      delete params.monitor_ip;
      delete params.port;
      Object.assign(configForm.config, params);
    }
    switch (pluginName) {
      case 'ElasticSearch':
        configForm.config.servers = [params.server];
        break;
      default:
        break;
    }
    configForm.config.interval = params.interval + 's';
    if (params.timeout) {
      configForm.config.timeout = params.timeout + 's';
    }
    try {
      setConfirmLoading(true);
      await post('/monitor/api/node_mgmt/update_instance_child_config/', {
        content: {
          config: configForm.config,
          plugin: configForm.plugin,
        },
        id: configForm.id,
      });
      message.success(t('common.successfullyModified'));
      handleCancel();
      onSuccess();
    } catch (error) {
      console.log(error);
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
            onClick={handleSubmit}
          >
            {t('common.confirm')}
          </Button>
          <Button onClick={handleCancel}>{t('common.cancel')}</Button>
        </div>
      }
    >
      <div className="px-[10px]">
        <Form ref={formRef} form={form} name="basic" layout="vertical">
          {formItems}
          <Form.Item required label={t('monitor.intergrations.interval')}>
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
              {t('monitor.intergrations.intervalDes')}
            </span>
          </Form.Item>
        </Form>
      </div>
    </OperateModal>
  );
});

UpdateConfig.displayName = 'UpdateConfig';

export default UpdateConfig;
