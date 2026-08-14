'use client';
import React from 'react';
import { Button } from 'antd';
import { EditOutlined, CheckOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import { RACK_ROOM_ASSET_PERMISSION_PATH } from '../rackRoomEdit';

interface EditToolbarProps {
  editing: boolean;
  onToggle: () => void;
  onAddDevice: () => void;
}

const EditToolbar: React.FC<EditToolbarProps> = ({
  editing,
  onToggle,
  onAddDevice,
}) => {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2">
      {editing && (
        <Button icon={<PlusOutlined />} onClick={onAddDevice}>
          {t('Model.networkTopoAddDevice')}
        </Button>
      )}
      <PermissionWrapper
        requiredPermissions={['Add Associate']}
        permissionPath={RACK_ROOM_ASSET_PERMISSION_PATH}
      >
        <Button
          type={editing ? 'primary' : 'default'}
          icon={editing ? <CheckOutlined /> : <EditOutlined />}
          onClick={onToggle}
        >
          {editing ? t('Model.networkTopoExitEdit') : t('Model.networkTopoEdit')}
        </Button>
      </PermissionWrapper>
    </div>
  );
};

export default EditToolbar;
