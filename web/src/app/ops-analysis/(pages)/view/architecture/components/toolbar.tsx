import React from 'react';
import { Button, Tooltip, Tag } from 'antd';
import {
  SaveOutlined,
  EditOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
} from '@ant-design/icons';
import { ArchitectureProps } from '@/app/ops-analysis/types/architecture';
import PermissionWrapper from '@/components/permission';
import { useTranslation } from '@/utils/i18n';

interface ArchitectureToolbarProps {
  selectedArchitecture: ArchitectureProps['selectedArchitecture'];
  isEditMode: boolean;
  isFullscreen: boolean;
  loading: boolean;
  onEdit: () => void;
  onSave: () => void;
  onFullscreenToggle: () => void;
}

const ArchitectureToolbar: React.FC<ArchitectureToolbarProps> = ({
  selectedArchitecture,
  isEditMode,
  isFullscreen,
  loading,
  onEdit,
  onSave,
  onFullscreenToggle,
}) => {
  const { t } = useTranslation();
  return (
    <div className="w-full mb-2 flex items-center justify-between rounded-lg shadow-sm p-3 border border-(--color-border-2) bg-(--color-bg-1)">
      {/* 左侧：架构图信息 */}
      <div className="flex-1 mr-8">
        {selectedArchitecture && (
          <div className="p-1 pt-0">
            <h2 className="text-lg font-semibold mb-1">
              {selectedArchitecture.name}
              {selectedArchitecture.is_build_in && (
                <Tag color="blue" className="ml-2 text-xs align-middle">
                  {t('common.builtIn')}
                </Tag>
              )}
            </h2>
            <p className="text-sm text-gray-500">
              {selectedArchitecture.desc || '--'}
            </p>
          </div>
        )}
      </div>

      {/* 右侧：工具栏 */}
      <div className="flex items-center space-x-2">
        <Tooltip
          title={
            isFullscreen ? t('common.exitFullscreen') : t('common.fullscreen')
          }
        >
          <Button
            type="text"
            icon={
              isFullscreen ? (
                <FullscreenExitOutlined style={{ fontSize: 16 }} />
              ) : (
                <FullscreenOutlined style={{ fontSize: 16 }} />
              )
            }
            onClick={onFullscreenToggle}
          />
        </Tooltip>
        <PermissionWrapper requiredPermissions={['EditChart']}>
          {isEditMode ? (
            <Button
              icon={<SaveOutlined />}
              loading={loading}
              onClick={onSave}
              type="primary"
            >
              {t('common.save')}
            </Button>
          ) : (
            <Tooltip title={t('common.edit')}>
              <Button
                type="text"
                icon={<EditOutlined style={{ fontSize: 16 }} />}
                onClick={onEdit}
                disabled={selectedArchitecture?.is_build_in}
              />
            </Tooltip>
          )}
        </PermissionWrapper>
      </div>
    </div>
  );
};

export default ArchitectureToolbar;
