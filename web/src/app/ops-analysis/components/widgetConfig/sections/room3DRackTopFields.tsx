'use client';

import React from 'react';
import { Form, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { Room3DRackTopField } from '@/app/ops-analysis/types/sceneWidget';
import { ROOM3D_RACK_TOP_FIELDS } from '@/app/ops-analysis/utils/room3DConfig';

const FIELD_LABEL_KEYS: Record<Room3DRackTopField, string> = {
  location: 'dashboard.room3DRackTopFieldLocation',
  name: 'dashboard.room3DRackTopFieldName',
  type: 'dashboard.room3DRackTopFieldType',
  state: 'dashboard.room3DRackTopFieldState',
};

export const Room3DRackTopFields = () => {
  const { t } = useTranslation();
  const options = ROOM3D_RACK_TOP_FIELDS.map((value) => ({
    value,
    label: t(FIELD_LABEL_KEYS[value]),
  }));

  return (
    <>
      <Form.Item
        label={t('dashboard.room3DRackTopLine1')}
        name={['room3D', 'rackTopLine1']}
        rules={[{ required: true }]}
      >
        <Select options={options} />
      </Form.Item>
      <Form.Item
        label={t('dashboard.room3DRackTopLine2')}
        name={['room3D', 'rackTopLine2']}
      >
        <Select
          allowClear
          options={options}
          placeholder={t('dashboard.room3DRackTopLine2Placeholder')}
        />
      </Form.Item>
    </>
  );
};
