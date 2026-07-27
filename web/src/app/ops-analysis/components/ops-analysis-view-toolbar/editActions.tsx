import React from 'react';
import { Button, Tooltip } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import { useTranslation } from '@/utils/i18n';

interface ViewToolbarEditActionsProps {
  isEditMode: boolean;
  loading?: boolean;
  editDisabled?: boolean;
  onEdit: () => void;
  onSave: () => void;
  onCancel?: () => void;
  permissionKeys?: string[];
  editTooltip?: string;
  editIcon?: React.ReactNode;
  saveIcon?: React.ReactNode;
  saveLabel?: string;
  cancelLabel?: string;
  editButtonClassName?: string;
  saveButtonClassName?: string;
  cancelButtonClassName?: string;
  editingActionsClassName?: string;
}

const ViewToolbarEditActions: React.FC<ViewToolbarEditActionsProps> = ({
  isEditMode,
  loading = false,
  editDisabled = false,
  onEdit,
  onSave,
  onCancel,
  permissionKeys = ['EditChart'],
  editTooltip,
  editIcon = <EditOutlined style={{ fontSize: 16 }} />,
  saveIcon,
  saveLabel,
  cancelLabel,
  editButtonClassName = '',
  saveButtonClassName = '',
  cancelButtonClassName = '',
  editingActionsClassName = 'ml-2 flex items-center gap-2',
}) => {
  const { t } = useTranslation();
  const resolvedSaveLabel = saveLabel || t('common.save');
  const resolvedCancelLabel = cancelLabel || t('common.cancel');

  return (
    <PermissionWrapper requiredPermissions={permissionKeys}>
      {isEditMode ? (
        <div className={editingActionsClassName}>
          {onCancel && (
            <Button onClick={onCancel} className={cancelButtonClassName}>
              {resolvedCancelLabel}
            </Button>
          )}
          <Button
            type="primary"
            icon={saveIcon}
            loading={loading}
            onClick={onSave}
            className={saveButtonClassName}
          >
            {resolvedSaveLabel}
          </Button>
        </div>
      ) : (
        <Tooltip title={editTooltip || t('common.edit')}>
          <Button
            type="text"
            icon={editIcon}
            onClick={onEdit}
            disabled={editDisabled}
            className={editButtonClassName}
          />
        </Tooltip>
      )}
    </PermissionWrapper>
  );
};

export default ViewToolbarEditActions;
