'use client';

import React, { useEffect } from 'react';
import { Button, Form, InputNumber, Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { ScreenViewportConfig } from '@/app/ops-analysis/types/screen';
import {
  SCREEN_VIEWPORT_PRESETS,
  isValidViewportSize,
} from '../utils/viewport';

interface ScreenConfigModalProps {
  open: boolean;
  viewport: ScreenViewportConfig;
  saving?: boolean;
  onCancel: () => void;
  onSave: (viewport: ScreenViewportConfig) => void;
}

interface ScreenConfigFormValues {
  preset: string;
  width: number;
  height: number;
}

const getPresetKey = (viewport: ScreenViewportConfig) =>
  SCREEN_VIEWPORT_PRESETS.find(
    (item) => item.width === viewport.width && item.height === viewport.height,
  )?.key || 'custom';

const ScreenConfigModal: React.FC<ScreenConfigModalProps> = ({
  open,
  viewport,
  saving = false,
  onCancel,
  onSave,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<ScreenConfigFormValues>();
  const activePresetKey = Form.useWatch('preset', form);
  const currentWidth = Form.useWatch('width', form);
  const currentHeight = Form.useWatch('height', form);

  useEffect(() => {
    if (!open) return;

    form.setFieldsValue({
      preset: getPresetKey(viewport),
      width: viewport.width,
      height: viewport.height,
    });
  }, [form, open, viewport]);

  const handlePresetSelect = (preset: {
    key: string;
    width: number;
    height: number;
  }) => {
    form.setFieldsValue({
      preset: preset.key,
      width: preset.width,
      height: preset.height,
    });
  };

  const markCustom = () => {
    form.setFieldValue('preset', 'custom');
  };

  const handleOk = async () => {
    const values = await form.validateFields();
    onSave({ width: values.width, height: values.height });
  };

  return (
    <Modal
      title={t('opsAnalysis.screen.canvasSettings')}
      open={open}
      width={560}
      centered
      getContainer={() => document.body}
      confirmLoading={saving}
      onCancel={onCancel}
      onOk={handleOk}
      okText={t('common.save')}
      cancelText={t('common.cancel')}
    >
      <div className="space-y-5 pt-1">
        <div>
          <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">
            {t('opsAnalysis.screen.resolutionPreset')}
          </div>
          <div className="flex flex-wrap gap-2">
            {SCREEN_VIEWPORT_PRESETS.map((preset) => (
              <Button
                key={preset.key}
                type={activePresetKey === preset.key ? 'primary' : 'default'}
                onClick={() => handlePresetSelect(preset)}
                className="rounded-full!"
              >
                {preset.label}
              </Button>
            ))}
            <Button
              type={activePresetKey === 'custom' ? 'primary' : 'default'}
              onClick={markCustom}
              className="rounded-full!"
            >
              {t('opsAnalysis.screen.customResolution')}
            </Button>
          </div>
        </div>

        <Form form={form} layout="vertical" className="m-0">
          <Form.Item name="preset" hidden>
            <input />
          </Form.Item>
          <div className="grid grid-cols-2 gap-3">
            <Form.Item
              name="width"
              label={t('opsAnalysis.screen.width')}
              className="mb-0"
              rules={[
                {
                  validator: (_, value) =>
                    isValidViewportSize(value)
                      ? Promise.resolve()
                      : Promise.reject(
                          new Error(t('opsAnalysis.screen.sizeInvalid')),
                        ),
                },
              ]}
            >
              <InputNumber
                precision={0}
                controls={false}
                placeholder="1920"
                className="w-full"
                onChange={markCustom}
              />
            </Form.Item>
            <Form.Item
              name="height"
              label={t('opsAnalysis.screen.height')}
              className="mb-0"
              rules={[
                {
                  validator: (_, value) =>
                    isValidViewportSize(value)
                      ? Promise.resolve()
                      : Promise.reject(
                          new Error(t('opsAnalysis.screen.sizeInvalid')),
                        ),
                },
              ]}
            >
              <InputNumber
                precision={0}
                controls={false}
                placeholder="1080"
                className="w-full"
                onChange={markCustom}
              />
            </Form.Item>
          </div>
        </Form>

        <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-2">
          <div className="text-xs text-[var(--color-text-3)]">
            {t('opsAnalysis.screen.currentResolution')}
          </div>
          <div className="mt-0.5 text-sm font-medium text-[var(--color-text-1)]">
            {isValidViewportSize(currentWidth) &&
            isValidViewportSize(currentHeight)
              ? `${currentWidth} × ${currentHeight}`
              : '--'}
          </div>
        </div>
      </div>
    </Modal>
  );
};

export default ScreenConfigModal;
