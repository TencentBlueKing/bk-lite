'use client';

import React from 'react';
import { Button, Space } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface Props {
  manageMode: boolean;
  dirty: boolean;
  saving: boolean;
  onEnter: () => void;
  onCancel: () => void;
  onSave: () => void;
}

const ManageToolbar: React.FC<Props> = ({ manageMode, dirty, saving, onEnter, onCancel, onSave }) => {
  const { t } = useTranslation();
  if (!manageMode) {
    return (
      <Button onClick={onEnter} className="ml-[8px]">
        {t('Model.manageLayout') || '管理排序'}
      </Button>
    );
  }
  return (
    <Space className="ml-[8px]">
      <Button onClick={onCancel} disabled={saving}>
        {t('common.cancel')}
      </Button>
      <Button type="primary" loading={saving} disabled={!dirty} onClick={onSave}>
        {t('common.save')}
      </Button>
    </Space>
  );
};

export default ManageToolbar;
