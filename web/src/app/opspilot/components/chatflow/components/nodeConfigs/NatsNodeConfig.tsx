import React from 'react';
import { Form, Input, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';

const { TextArea } = Input;

const ICON_TYPES = ['duihuazhinengti', 'a-zhinengti', 'zhinengtitubiao', 'zhinengti1', 'zhinengti2'];

export const NatsNodeConfig: React.FC<{ form?: any }> = ({ form }) => {
  const { t } = useTranslation();

  // 条件渲染 + 联动必填：仅当 exposeAsWebChat=true 时显示应用名/图标/描述，
  // 且 require=true，避免用户开启开关后忘填导致后续 sync 生不成应用。
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
              <Form.Item
                name="appName"
                label={t('chatflow.nodeConfig.natsOptionalAppName')}
                rules={[{ required: true, message: t('chatflow.nodeConfig.exposeAsWebChatAppNameRequired') }]}
              >
                <Input placeholder={t('chatflow.nodeConfig.natsOptionalAppNamePlaceholder')} />
              </Form.Item>
              <Form.Item
                name="appIcon"
                label={t('chatflow.nodeConfig.appIcon')}
                rules={[{ required: true, message: t('chatflow.nodeConfig.pleaseSelectAppIcon') }]}
              >
                <Form.Item noStyle shouldUpdate={(prev, curr) => prev.appIcon !== curr.appIcon}>
                  {() => (
                    <div className="flex gap-3">
                      {ICON_TYPES.map(iconType => (
                        <div
                          key={iconType}
                          onClick={() => {
                            if (form) {
                              form.setFieldValue('appIcon', iconType);
                              form.validateFields(['appIcon']);
                            }
                          }}
                          className={`w-10 h-10 flex items-center justify-center rounded cursor-pointer transition-all ${
                            getFieldValue('appIcon') === iconType
                              ? 'border-2 border-blue-500 bg-blue-50/50'
                              : 'border border-gray-200 hover:border-gray-300'
                          }`}
                        >
                          <Icon type={iconType} className="text-2xl" />
                        </div>
                      ))}
                    </div>
                  )}
                </Form.Item>
              </Form.Item>
              <Form.Item
                name="appDescription"
                label={t('chatflow.nodeConfig.natsOptionalAppDescription')}
                rules={[{ required: true, message: t('chatflow.nodeConfig.exposeAsWebChatAppDescriptionRequired') }]}
              >
                <TextArea rows={3} placeholder={t('chatflow.nodeConfig.natsOptionalAppDescriptionPlaceholder')} />
              </Form.Item>
            </>
          ) : null
        }
      </Form.Item>
    </>
  );
};
