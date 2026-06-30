"use client";

import React, { useEffect } from "react";
import {
  Button,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  message,
} from "antd";
import { useTranslation } from "@/utils/i18n";
import type {
  ScreenDecorationsConfig,
  ScreenViewportConfig,
} from "@/app/ops-analysis/types/screen";
import {
  SCREEN_VIEWPORT_PRESETS,
  isValidViewportSize,
} from "../utils/viewport";

interface ScreenConfigModalProps {
  open: boolean;
  viewport: ScreenViewportConfig;
  decorations: ScreenDecorationsConfig;
  saving?: boolean;
  onCancel: () => void;
  onSave: (payload: {
    viewport: ScreenViewportConfig;
    decorations: ScreenDecorationsConfig;
  }) => void;
  canSaveViewport?: (viewport: ScreenViewportConfig) => boolean;
}

interface ScreenConfigFormValues {
  preset: string;
  width: number;
  height: number;
  title: string;
  showTitle: boolean;
  showClock: boolean;
}

const getPresetKey = (viewport: ScreenViewportConfig) =>
  SCREEN_VIEWPORT_PRESETS.find(
    (item) => item.width === viewport.width && item.height === viewport.height,
  )?.key || "custom";

const ScreenConfigModal: React.FC<ScreenConfigModalProps> = ({
  open,
  viewport,
  decorations,
  saving = false,
  onCancel,
  onSave,
  canSaveViewport,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<ScreenConfigFormValues>();
  const activePresetKey = Form.useWatch("preset", form);

  useEffect(() => {
    if (!open) return;

    form.setFieldsValue({
      preset: getPresetKey(viewport),
      width: viewport.width,
      height: viewport.height,
      title: decorations.title || "",
      showTitle: decorations.showTitle !== false,
      showClock: decorations.showClock !== false,
    });
  }, [decorations, form, open, viewport]);

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
    form.setFieldValue("preset", "custom");
  };

  const handleOk = async () => {
    const values = await form.validateFields();
    const nextViewport = { width: values.width, height: values.height };
    if (canSaveViewport && !canSaveViewport(nextViewport)) {
      message.error(t("opsAnalysis.screen.viewportContainsOverflow"));
      return;
    }
    onSave({
      viewport: nextViewport,
      decorations: {
        title: values.title,
        showTitle: values.showTitle,
        showClock: values.showClock,
      },
    });
  };

  return (
    <>
      <Modal
        title={t("opsAnalysis.screen.canvasSettings")}
        open={open}
        width={620}
        centered
        className="screen-config-modal"
        getContainer={() => document.body}
        confirmLoading={saving}
        onCancel={onCancel}
        onOk={handleOk}
        okText={t("common.save")}
        cancelText={t("common.cancel")}
      >
        <div className="screen-config-modal__stack">
          <Form form={form} layout="vertical" className="m-0">
            <Form.Item name="preset" hidden>
              <input />
            </Form.Item>
            <div className="screen-config-section">
              <div className="screen-config-section__title">
                {t("opsAnalysis.screen.resolutionPreset")}
              </div>
              <div className="flex flex-wrap gap-2.5">
                {SCREEN_VIEWPORT_PRESETS.map((preset) => (
                  <Button
                    key={preset.key}
                    type={
                      activePresetKey === preset.key ? "primary" : "default"
                    }
                    onClick={() => handlePresetSelect(preset)}
                    className="h-8 rounded-full! px-4"
                  >
                    {preset.label}
                  </Button>
                ))}
                <Button
                  type={activePresetKey === "custom" ? "primary" : "default"}
                  onClick={markCustom}
                  className="h-8 rounded-full! px-4"
                >
                  {t("opsAnalysis.screen.customResolution")}
                </Button>
              </div>
              <div className="screen-config-section__grid">
                <Form.Item
                  name="width"
                  label={t("opsAnalysis.screen.width")}
                  className="mb-0"
                  rules={[
                    {
                      validator: (_, value) =>
                        isValidViewportSize(value)
                          ? Promise.resolve()
                          : Promise.reject(
                              new Error(t("opsAnalysis.screen.sizeInvalid")),
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
                  label={t("opsAnalysis.screen.height")}
                  className="mb-0"
                  rules={[
                    {
                      validator: (_, value) =>
                        isValidViewportSize(value)
                          ? Promise.resolve()
                          : Promise.reject(
                              new Error(t("opsAnalysis.screen.sizeInvalid")),
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
            </div>
          </Form>

          <Form form={form} layout="vertical" className="m-0">
            <div className="screen-config-section">
              <Form.Item
                name="title"
                label={t("opsAnalysis.screen.screenTitle")}
                className="mb-4"
              >
                <Input
                  maxLength={64}
                  placeholder={t("opsAnalysis.screen.defaultTitle")}
                />
              </Form.Item>
              <div className="flex flex-wrap gap-x-8 gap-y-3">
                <Form.Item
                  name="showTitle"
                  valuePropName="checked"
                  className="mb-0"
                >
                  <Checkbox>{t("opsAnalysis.screen.showTitle")}</Checkbox>
                </Form.Item>
                <Form.Item
                  name="showClock"
                  valuePropName="checked"
                  className="mb-0"
                >
                  <Checkbox>{t("opsAnalysis.screen.showClock")}</Checkbox>
                </Form.Item>
              </div>
            </div>
          </Form>
        </div>
      </Modal>
      <style>{`
        .screen-config-modal .ant-modal-content {
          border-radius: 14px;
        }

        .screen-config-modal .ant-modal-header {
          margin-bottom: 18px;
        }

        .screen-config-modal .ant-modal-body {
          padding-top: 2px;
        }

        .screen-config-modal__stack {
          display: flex;
          flex-direction: column;
          gap: 18px;
          padding-top: 4px;
        }

        .screen-config-section {
          border: 1px solid var(--color-border-1);
          border-radius: 12px;
          background: var(--color-fill-1);
          padding: 16px;
        }

        .screen-config-section__title {
          margin-bottom: 14px;
          color: var(--color-text-1);
          font-size: 14px;
          font-weight: 600;
          line-height: 22px;
        }

        .screen-config-section__grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 20px;
          margin-top: 18px;
          border-top: 1px solid var(--color-border-1);
          padding-top: 16px;
        }

        .screen-config-modal .ant-form-item-label {
          padding-bottom: 6px;
        }

        .screen-config-modal .ant-form-item-label > label {
          color: var(--color-text-1);
          font-size: 14px;
          font-weight: 600;
        }

        .screen-config-modal .ant-input,
        .screen-config-modal .ant-input-number {
          border-radius: 8px;
        }
      `}</style>
    </>
  );
};

export default ScreenConfigModal;
