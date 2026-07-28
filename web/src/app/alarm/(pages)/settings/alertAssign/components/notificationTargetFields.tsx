'use client';

import React from 'react';
import { Checkbox, Form, Radio, Select } from 'antd';
import GroupTreeSelect from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import type { NotificationTargetType } from './notificationTarget';

interface Option {
  label: string;
  value: string;
}

interface NotificationTargetFieldsProps {
  namePrefix?: Array<string | number>;
  watchPrefix?: Array<string | number>;
  personnelOptions: Option[];
  typeLabel: string;
}

const NotificationTargetFields: React.FC<NotificationTargetFieldsProps> = ({
  namePrefix = [],
  watchPrefix = namePrefix,
  personnelOptions,
  typeLabel,
}) => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const fieldName = (name: string) => [...namePrefix, name];
  const watchedFieldName = (name: string) => [...watchPrefix, name];
  const targetType =
    Form.useWatch(watchedFieldName('target_type'), form) || 'user';

  const handleTypeChange = (type: NotificationTargetType) => {
    if (type === 'organization') {
      form.setFieldValue(watchedFieldName('personnel'), []);
    } else {
      form.setFieldValue(watchedFieldName('organization_ids'), []);
      form.setFieldValue(watchedFieldName('include_children'), false);
    }
  };

  return (
    <>
      <Form.Item
        name={fieldName('target_type')}
        label={typeLabel}
        initialValue="user"
        rules={[{ required: true, message: t('common.selectTip') }]}
      >
        <Radio.Group
          optionType="button"
          buttonStyle="solid"
          onChange={(event) =>
            handleTypeChange(event.target.value as NotificationTargetType)
          }
          options={[
            {
              label: t('settings.assignStrategy.targetUser'),
              value: 'user',
            },
            {
              label: t('settings.assignStrategy.targetOrganization'),
              value: 'organization',
            },
          ]}
        />
      </Form.Item>

      {targetType === 'organization' ? (
        <>
          <Form.Item
            name={fieldName('organization_ids')}
            label={t('settings.assignStrategy.organizationSelect')}
            rules={[
              {
                required: true,
                message: t('settings.assignStrategy.organizationRequired'),
              },
            ]}
          >
            <GroupTreeSelect
              multiple
              showSearch
              allowClear
              placeholder={t('settings.assignStrategy.organizationRequired')}
            />
          </Form.Item>
          <Form.Item
            name={fieldName('include_children')}
            valuePropName="checked"
            initialValue={false}
          >
            <Checkbox>
              {t('settings.assignStrategy.includeChildOrganizations')}
            </Checkbox>
          </Form.Item>
        </>
      ) : (
        <Form.Item
          name={fieldName('personnel')}
          label={t('settings.assignStrategy.userSelect')}
          rules={[
            {
              required: true,
              message: t('settings.assignStrategy.userRequired'),
            },
          ]}
        >
          <Select
            mode="multiple"
            options={personnelOptions}
            placeholder={t('settings.assignStrategy.userRequired')}
            filterOption={(input, option) =>
              (option?.label as string)
                ?.toLowerCase()
                .includes(input.toLowerCase())
            }
          />
        </Form.Item>
      )}
    </>
  );
};

export default NotificationTargetFields;
