import React from 'react';
import { Button, Input, InputNumber, Modal } from 'antd';
import type { TopologyViewportConfig } from '@/app/ops-analysis/types/topology';
import { DEFAULT_TOPOLOGY_LETTERBOX_COLOR } from '../utils/viewport';
import { PRESENTATION_PRESETS } from '../hooks/useTopologyPresentation';

interface TopologyPresentationModalProps {
  activePresetKey?: string;
  draft: TopologyViewportConfig;
  open: boolean;
  t: (key: string) => string;
  onCancel: () => void;
  onClear: () => void;
  onConfirm: () => void;
  onDraftChange: (patch: { width?: number; height?: number }) => void;
  onDraftColorChange: React.Dispatch<
    React.SetStateAction<TopologyViewportConfig>
  >;
  onPresetSelect: (preset: { width: number; height: number }) => void;
}

const TopologyPresentationModal = ({
  activePresetKey,
  draft,
  open,
  t,
  onCancel,
  onClear,
  onConfirm,
  onDraftChange,
  onDraftColorChange,
  onPresetSelect,
}: TopologyPresentationModalProps) => {
  return (
    <Modal
      open={open}
      centered
      title={t('topology.presentationConfig')}
      onCancel={onCancel}
      footer={[
        <Button key="clear" onClick={onClear}>
          {t('topology.clearPresentationConfig')}
        </Button>,
        <Button key="cancel" onClick={onCancel}>
          {t('common.cancel')}
        </Button>,
        <Button key="confirm" type="primary" onClick={onConfirm}>
          {t('common.confirm')}
        </Button>,
      ]}
    >
      <div className="space-y-4 pt-1">
        <div>
          <div className="mb-2 text-sm font-medium text-(--color-text-1)">
            {t('topology.commonResolutions')}
          </div>
          <div className="flex flex-wrap gap-2">
            {PRESENTATION_PRESETS.map((preset) => (
              <Button
                key={preset.key}
                type={activePresetKey === preset.key ? 'primary' : 'default'}
                onClick={() => onPresetSelect(preset)}
                className="rounded-full!"
              >
                {preset.label}
              </Button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="mb-1 text-sm text-(--color-text-2)">
              {t('topology.fixedResolutionWidth')}
            </div>
            <InputNumber
              min={1}
              precision={0}
              controls={false}
              value={draft.width}
              placeholder="1920"
              className="w-full"
              onChange={(value) =>
                onDraftChange({
                  width: typeof value === 'number' ? value : undefined,
                })
              }
            />
          </div>
          <div>
            <div className="mb-1 text-sm text-(--color-text-2)">
              {t('topology.fixedResolutionHeight')}
            </div>
            <InputNumber
              min={1}
              precision={0}
              controls={false}
              value={draft.height}
              placeholder="1080"
              className="w-full"
              onChange={(value) =>
                onDraftChange({
                  height: typeof value === 'number' ? value : undefined,
                })
              }
            />
          </div>
        </div>

        <div>
          <div className="mb-1 text-sm text-(--color-text-2)">
            {t('topology.fixedResolutionBackground')}
          </div>
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={draft.letterboxColor || DEFAULT_TOPOLOGY_LETTERBOX_COLOR}
              aria-label={t('topology.fixedResolutionBackground')}
              className="h-10 w-14 cursor-pointer rounded border border-(--color-border-1) bg-transparent p-1"
              onChange={(event) =>
                onDraftColorChange((prev) => ({
                  ...prev,
                  letterboxColor: event.target.value,
                }))
              }
            />
            <Input
              value={draft.letterboxColor || DEFAULT_TOPOLOGY_LETTERBOX_COLOR}
              placeholder={DEFAULT_TOPOLOGY_LETTERBOX_COLOR}
              onChange={(event) =>
                onDraftColorChange((prev) => ({
                  ...prev,
                  letterboxColor: event.target.value,
                }))
              }
            />
          </div>
        </div>
      </div>
    </Modal>
  );
};

export default TopologyPresentationModal;
