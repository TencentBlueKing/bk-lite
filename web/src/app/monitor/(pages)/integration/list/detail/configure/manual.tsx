import React, { useState, useEffect, useMemo } from 'react';
import { Form, Button, message, InputNumber, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { TIMEOUT_UNITS } from '@/app/monitor/constants/integration';
import { useSearchParams } from 'next/navigation';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/monitor/api/integration';
import CodeEditor from '@/app/monitor/components/codeEditor';
import { TableDataItem } from '@/app/monitor/types';
const { Option } = Select;
import Permission from '@/components/permission';
import { IntegrationAccessProps } from '@/app/monitor/types/integration';
import { useMonitorConfig } from '@/app/monitor/hooks/integration/index';
import { cloneDeep } from 'lodash';

const AutomaticConfiguration: React.FC<IntegrationAccessProps> = ({
  showInterval = true,
}) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { isLoading } = useApiClient();
  const { checkMonitorInstance } = useIntegrationApi();
  const configs = useMonitorConfig();
  const pluginName = searchParams.get('plugin_name') || '';
  const objId = searchParams.get('id') || '';
  const objectName = searchParams.get('name') || '';
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [configMsg, setConfigMsg] = useState<string>('');

  const configsInfo = useMemo(() => {
    return configs.getPlugin({
      objectName,
      mode: 'manual',
      pluginName,
    });
  }, [pluginName, objectName]);

  const collectType = useMemo(() => {
    return configsInfo.collect_type || '';
  }, [configsInfo]);

  const formItems = useMemo(() => {
    return configsInfo.formItems;
  }, [configsInfo]);

  useEffect(() => {
    if (isLoading) return;
    initData();
  }, [isLoading]);

  const initData = () => {
    form.setFieldsValue({
      interval: collectType === 'http' ? 60 : 10,
      ...configsInfo.defaultForm,
    });
  };

  const handleSave = () => {
    form.validateFields().then((values) => {
      const params = cloneDeep(values);
      getConfigText(params);
    });
  };

  const getConfigText = async (params: TableDataItem) => {
    try {
      setConfirmLoading(true);
      await checkMonitorInstance(objId, configsInfo.getParams(params));
      setConfigMsg(configsInfo.getConfigText(params));
      message.success(t('common.successfullyAdded'));
    } finally {
      setConfirmLoading(false);
    }
  };

  return (
    <div className="px-[10px]">
      <Form form={form} name="basic" layout="vertical">
        {formItems && (
          <p className="mb-[20px]">
            {t('monitor.integrations.configureStepIntro')}
          </p>
        )}
        {formItems}
        {showInterval && (
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
        )}
      </Form>
      <Permission requiredPermissions={['Add']}>
        <Button type="primary" loading={confirmLoading} onClick={handleSave}>
          {t('monitor.integrations.generateConfiguration')}
        </Button>
      </Permission>
      {!!configMsg && (
        <CodeEditor
          className="mt-[10px]"
          mode="python"
          theme="monokai"
          name="editor"
          width="100%"
          height="300px"
          readOnly
          value={configMsg}
          showCopy
        />
      )}
    </div>
  );
};

export default AutomaticConfiguration;
