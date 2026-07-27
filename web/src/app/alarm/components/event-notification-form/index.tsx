import React, { useMemo } from 'react';
import { Form, Switch, Button, Select } from 'antd';
import SelectableCardGrid, {
  type SelectableCardItem,
} from '@/components/selectable-card-grid';

const { Option } = Select;

const getChannelIcon = (channelType: string): string => {
  const iconMap: Record<string, string> = {
    email: 'youjian',
    enterprise_wechat_bot: 'qiwei2',
    feishu_bot: 'feishu',
    dingtalk_bot: 'dingding',
    custom_webhook: 'webhook',
    nats: 'dongzuo1',
  };
  return iconMap[channelType] || 'jiqiren3';
};

export interface EventNotificationChannel {
  id: string | number;
  name: string;
  description?: string;
  channel_type: string;
}

export interface EventNotificationUser {
  id: string | number;
  display_name?: string;
}

export type EventNotifierMode = 'none' | 'users' | 'tags';

export interface EventNotificationFormCopy {
  configDescription: React.ReactNode;
  configLabel: React.ReactNode;
  channelLabel: React.ReactNode;
  notifierLabel: React.ReactNode;
  emptyStatePrefix: React.ReactNode;
  emptyStateLinkLabel: React.ReactNode;
  emptyStateSuffix: React.ReactNode;
  notifierPlaceholder: string;
  notifierTagsPlaceholder?: string;
  requiredMessage: string;
}

export interface EventNotificationFormProps {
  channelFieldName: string;
  channelList: EventNotificationChannel[];
  channelSelectionMode: 'single' | 'multiple';
  copy: EventNotificationFormCopy;
  getChannelTagLabel?: (channelType: string) => string;
  notifierFieldName?: string;
  onLinkToSystemManage: () => void;
  resolveNotifierMode: (channelTypes: string[]) => EventNotifierMode;
  userList: EventNotificationUser[];
  enableFieldName?: string;
  cardGridStyle?: React.CSSProperties;
  selectStyle?: React.CSSProperties;
  clearNotifierOnChannelChange?: 'always' | 'never' | 'when-hidden';
}

const normalizeSelection = (
  value: string | number | Array<string | number> | undefined
): Array<string | number> => {
  if (Array.isArray(value)) {
    return value;
  }
  if (value === undefined || value === null) {
    return [];
  }
  return [value];
};

const EventNotificationForm: React.FC<EventNotificationFormProps> = ({
  channelFieldName,
  channelList,
  channelSelectionMode,
  copy,
  getChannelTagLabel,
  notifierFieldName = 'notice_users',
  onLinkToSystemManage,
  resolveNotifierMode,
  userList,
  enableFieldName = 'notice',
  cardGridStyle,
  selectStyle,
  clearNotifierOnChannelChange = 'never',
}) => {
  const form = Form.useFormInstance();

  const channelCardData: SelectableCardItem[] = useMemo(() => {
    return channelList.map((item) => ({
      icon: getChannelIcon(item.channel_type),
      title: item.name,
      tag: getChannelTagLabel?.(item.channel_type) || item.channel_type,
      description: item.description,
      value: item.id,
    }));
  }, [channelList, getChannelTagLabel]);

  const handleChannelChange = (
    nextValue: string | number | Array<string | number>
  ) => {
    const normalizedValues = normalizeSelection(nextValue);
    const nextFieldValue =
      channelSelectionMode === 'single' ? normalizedValues[0] : normalizedValues;
    form.setFieldValue(channelFieldName, nextFieldValue);

    const nextChannelTypes = channelList
      .filter((item) => normalizedValues.includes(item.id))
      .map((item) => item.channel_type);
    const nextNotifierMode = resolveNotifierMode(nextChannelTypes);

    if (clearNotifierOnChannelChange === 'always') {
      form.setFieldValue(notifierFieldName, []);
    } else if (
      clearNotifierOnChannelChange === 'when-hidden' &&
      nextNotifierMode === 'none'
    ) {
      form.setFieldValue(notifierFieldName, []);
    }
  };

  return (
    <>
      <Form.Item label={copy.configLabel}>
        <Form.Item name={enableFieldName} noStyle>
          <Switch />
        </Form.Item>
        <div className="mt-[10px] text-[var(--color-text-3)]">
          {copy.configDescription}
        </div>
      </Form.Item>
      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues[enableFieldName] !== currentValues[enableFieldName]
        }
      >
        {({ getFieldValue }) =>
          getFieldValue(enableFieldName) ? (
            <>
              <Form.Item
                label={copy.channelLabel}
                name={channelFieldName}
                rules={[
                  {
                    required: true,
                    message: copy.requiredMessage,
                  },
                ]}
              >
                {channelList.length ? (
                  <SelectableCardGrid
                    data={channelCardData}
                    value={getFieldValue(channelFieldName)}
                    style={cardGridStyle}
                    selectionMode={channelSelectionMode}
                    onChange={handleChannelChange}
                  />
                ) : (
                  <span>
                    {copy.emptyStatePrefix}
                    <Button
                      type="link"
                      className="mx-[4px] p-0"
                      onClick={onLinkToSystemManage}
                    >
                      {copy.emptyStateLinkLabel}
                    </Button>
                    {copy.emptyStateSuffix}
                  </span>
                )}
              </Form.Item>
              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) =>
                  prevValues[channelFieldName] !== currentValues[channelFieldName]
                }
              >
                {({ getFieldValue }) => {
                  const selectedIds = normalizeSelection(
                    getFieldValue(channelFieldName)
                  );
                  const selectedChannelTypes = channelList
                    .filter((item) => selectedIds.includes(item.id))
                    .map((item) => item.channel_type);
                  const notifierMode = resolveNotifierMode(selectedChannelTypes);

                  if (notifierMode === 'none') {
                    return null;
                  }

                  return (
                    <Form.Item
                      label={copy.notifierLabel}
                      name={notifierFieldName}
                      rules={[
                        {
                          required: true,
                          message: copy.requiredMessage,
                        },
                      ]}
                    >
                      {notifierMode === 'users' ? (
                        <Select
                          style={selectStyle}
                          showSearch
                          allowClear
                          mode="multiple"
                          maxTagCount="responsive"
                          placeholder={copy.notifierPlaceholder}
                          virtual
                          filterOption={(input, option) => {
                            const user = userList.find(
                              (item) => item.id === option?.value
                            );
                            if (!user) return false;
                            const searchText = input.toLowerCase();
                            return (
                              user.display_name?.toLowerCase() || ''
                            ).includes(searchText);
                          }}
                          optionLabelProp="label"
                        >
                          {userList.map((item) => (
                            <Option
                              value={item.id}
                              key={item.id}
                              label={item.display_name}
                            >
                              {item.display_name}
                            </Option>
                          ))}
                        </Select>
                      ) : (
                        <Select
                          style={selectStyle}
                          mode="tags"
                          placeholder={
                            copy.notifierTagsPlaceholder ||
                            copy.notifierPlaceholder
                          }
                          suffixIcon={null}
                          open={false}
                        />
                      )}
                    </Form.Item>
                  );
                }}
              </Form.Item>
            </>
          ) : null
        }
      </Form.Item>
    </>
  );
};

export default EventNotificationForm;
export {
  createLogEventNotificationPreset,
  createMonitorEventNotificationPreset,
} from './presets';
