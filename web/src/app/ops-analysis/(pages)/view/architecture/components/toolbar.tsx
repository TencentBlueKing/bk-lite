import React from 'react';
import { Button, Dropdown, Switch, Tooltip } from 'antd';
import TimeSelector from '@/components/time-selector';
import {
  EditOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  ShareAltOutlined,
  DownOutlined,
  PlusOutlined,
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
  onAddResources?: () => void;
  editExtra?: React.ReactNode;
  bindingMeter?: {
    bound: number;
    total: number;
    highlightUnbound: boolean;
    unbound: number;
    onToggleHighlight: () => void;
  };
  showMetrics?: boolean;
  onShowMetricsChange?: (enabled: boolean) => void;
  onRefresh?: () => void;
  onFrequencyChange?: (intervalMs: number) => void;
  frequenceValue?: number;
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
  onAddResources,
  editExtra,
  bindingMeter,
  showMetrics = true,
  onShowMetricsChange,
  onRefresh,
  onFrequencyChange,
  frequenceValue = 0,
}) => {
  const { t } = useTranslation();
  const iconButtonClassName =
    'h-8 w-8 min-w-8 px-0! flex items-center justify-center rounded-full!';
  const bindingMeterTrigger = bindingMeter ? (
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
      <button
        type="button"
        data-testid="architecture-binding-meter"
        className="inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent px-1 text-sm text-[var(--color-text-2)]"
      >
        {t('opsAnalysis.architecture.bindingCount', undefined, {
          bound: bindingMeter.bound,
          total: bindingMeter.total,
        })}
        <DownOutlined className="text-[10px]" />
      </button>
    </Dropdown>
  ) : null;

  return (
    <div className="flex items-center gap-2">
      {!shareMode && !isEditMode && onRefresh && onFrequencyChange ? (
        <TimeSelector
          onlyRefresh
          frequenceValue={frequenceValue}
          onRefresh={onRefresh}
          onFrequenceChange={onFrequencyChange}
        />
      ) : null}
      {!shareMode && !isEditMode && onShowMetricsChange ? (
        <label className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-2)]">
          <span>{t('opsAnalysis.architecture.showMetrics')}</span>
          <Switch size="small" checked={showMetrics} onChange={onShowMetricsChange} />
        </label>
      ) : null}
      {isEditMode ? bindingMeterTrigger : null}
      <div className="flex items-center gap-0.5">
        <Tooltip
          title={
            isFullscreen ? t('common.exitFullscreen') : t('common.fullscreen')
          }
        >
          <Button
            type="text"
            className={iconButtonClassName}
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
              className={iconButtonClassName}
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
                className={iconButtonClassName}
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
            {editExtra}
            {onAddResources ? (
              <Button
                type="default"
                icon={<PlusOutlined />}
                onClick={onAddResources}
                data-testid="architecture-add-resources"
              >
                {t('opsAnalysis.architecture.addResources')}
              </Button>
            ) : null}
            {onCancel && (
              <Button type="default" onClick={onCancel}>
                {t('common.cancel')}
              </Button>
            )}
            <Button
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
  );
};

export default ArchitectureToolbar;
