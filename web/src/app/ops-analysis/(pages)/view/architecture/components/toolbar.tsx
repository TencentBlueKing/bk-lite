import React from 'react';
import { Button, Dropdown, Tooltip, Tag } from 'antd';
import {
  SaveOutlined,
  EditOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  ShareAltOutlined,
  DownOutlined,
} from '@ant-design/icons';
import { ArchitectureProps } from '@/app/ops-analysis/types/architecture';
import PermissionWrapper from '@/components/permission';
import { useTranslation } from '@/utils/i18n';

interface ArchitectureToolbarProps {
  selectedArchitecture: ArchitectureProps['selectedArchitecture'];
  isEditMode: boolean;
  isFullscreen: boolean;
  shareMode?: boolean;
  shareLoading?: boolean;
  onOpenShare?: () => void;
  loading: boolean;
  onEdit: () => void;
  onCancel?: () => void;
  onSave: () => void;
  onFullscreenToggle: () => void;
  editExtra?: React.ReactNode;
  bindingMeter?: {
    bound: number;
    total: number;
    highlightUnbound: boolean;
    unbound: number;
    onToggleHighlight: () => void;
  };
}

const ArchitectureToolbar: React.FC<ArchitectureToolbarProps> = ({
  selectedArchitecture,
  isEditMode,
  isFullscreen,
  shareMode = false,
  shareLoading = false,
  onOpenShare,
  loading,
  onEdit,
  onCancel,
  onSave,
  onFullscreenToggle,
  editExtra,
  bindingMeter,
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
            <p className="text-sm text-[var(--color-text-3)]">
              {selectedArchitecture.desc || '--'}
            </p>
          </div>
        )}
      </div>

      {/* 右侧：工具栏 */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-0.5">
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
          {!shareMode && !isEditMode && onOpenShare && (
            <Tooltip title={t('dashboard.share')}>
              <Button
                type="text"
                icon={<ShareAltOutlined style={{ fontSize: 16 }} />}
                loading={shareLoading}
                disabled={shareLoading}
                aria-label={t('dashboard.share')}
                onClick={onOpenShare}
              />
            </Tooltip>
          )}
          {!shareMode && !isEditMode && (
            <PermissionWrapper requiredPermissions={['EditChart']}>
              <Tooltip title={t('common.edit')}>
                <Button
                  type="text"
                  icon={<EditOutlined style={{ fontSize: 16 }} />}
                  onClick={onEdit}
                  disabled={selectedArchitecture?.is_build_in}
                />
              </Tooltip>
            </PermissionWrapper>
          )}
        </div>
        {!shareMode && isEditMode && (
          <PermissionWrapper requiredPermissions={['EditChart']}>
            <div className="flex items-center gap-2">
              {bindingMeter ? (
                <Dropdown
                  trigger={['click']}
                  menu={{
                    items: [{
                      key: 'highlight',
                      label: t('opsAnalysis.architecture.highlightUnbound', undefined, {
                        count: bindingMeter.unbound,
                      }),
                    }],
                    selectedKeys: bindingMeter.highlightUnbound ? ['highlight'] : [],
                    onClick: () => bindingMeter.onToggleHighlight(),
                  }}
                >
                  <Button data-testid="architecture-binding-meter">
                    {t('opsAnalysis.architecture.bindingCount', undefined, {
                      bound: bindingMeter.bound,
                      total: bindingMeter.total,
                    })}
                    <DownOutlined />
                  </Button>
                </Dropdown>
              ) : null}
              {editExtra}
              {onCancel && (
                <Button type="default" onClick={onCancel}>
                  {t('common.cancel')}
                </Button>
              )}
              <Button
                icon={<SaveOutlined />}
                loading={loading}
                onClick={onSave}
                type="primary"
              >
                {t('common.save')}
              </Button>
            </div>
          </PermissionWrapper>
        )}
      </div>
    </div>
  );
};

export default ArchitectureToolbar;
