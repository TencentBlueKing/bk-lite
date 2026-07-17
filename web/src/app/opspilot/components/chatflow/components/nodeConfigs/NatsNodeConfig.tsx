import React from 'react';
import { Form, Input, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';

const { TextArea } = Input;

export const NatsNodeConfig: React.FC = () => {
  const { t } = useTranslation();

  // Form.useWatchValue 让 field 状态驱动条件渲染：仅当 exposeAsWebChat=true 时显示 Web 应用名/描述字段。
  return (
    <>
      <Form.Item
        name="exposeAsWebChat"
        label={t('chatflow.nodeConfig.exposeAsWebChat')}
        valuePropName="checked"
        tooltip={t('chatflow.nodeConfig.exposeAsWebChatTooltip')}
      >
        <Switch />
      </Form.Item>
      <Form.Item
        shouldUpdate={(prev, curr) => prev.exposeAsWebChat !== curr.exposeAsWebChat}
        noStyle
      >
        {({ getFieldValue }) =>
          getFieldValue('exposeAsWebChat') ? (
            <>
              <Form.Item name="appName" label={t('chatflow.nodeConfig.natsOptionalAppName')}>
                <Input placeholder={t('chatflow.nodeConfig.natsOptionalAppNamePlaceholder')} />
              </Form.Item>
              <Form.Item name="appDescription" label={t('chatflow.nodeConfig.natsOptionalAppDescription')}>
                <TextArea rows={3} placeholder={t('chatflow.nodeConfig.natsOptionalAppDescriptionPlaceholder')} />
              </Form.Item>
            </>
          ) : null
        }
      </Form.Item>
    </>
  );
};
