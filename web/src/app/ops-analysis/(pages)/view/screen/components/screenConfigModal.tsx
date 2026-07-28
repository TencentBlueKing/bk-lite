"use client";

import React, { useEffect } from "react";
import {
  Button,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  Segmented,
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
import {
  SCREEN_THEME_OPTIONS,
  resolveScreenThemeId,
} from "../utils/screenTheme";
import type { ScreenThemeId } from "@/app/ops-analysis/types/screen";

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
  theme: ScreenThemeId;
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
  const showTitle = Form.useWatch("showTitle", form);

  useEffect(() => {
    if (!open) return;

    form.setFieldsValue({
      preset: getPresetKey(viewport),
      width: viewport.width,
      height: viewport.height,
      theme: resolveScreenThemeId(viewport.theme),
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
    const nextViewport = {
      width: values.width,
      height: values.height,
      theme: resolveScreenThemeId(values.theme),
    };
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
        okText={t("common.confirm")}
        cancelText={t("common.cancel")}
        styles={{
          body: { maxHeight: "calc(100vh - 220px)", overflowY: "auto" },
        }}
      >
        <div className="screen-config-modal__stack">
          <Form form={form} layout="vertical" className="screen-config-form m-0">
            <Form.Item name="preset" hidden>
              <input />
            </Form.Item>
            <div className="screen-config-section">
              <Form.Item
                name="theme"
                label={t("opsAnalysis.screen.canvasTheme")}
                className="mb-0"
              >
                <Segmented
                  block
                  className="w-60 max-w-full"
                  options={SCREEN_THEME_OPTIONS.map((theme) => ({
                    label: (
                      <span className="screen-config-theme-option">
                        <span
                          className="screen-config-theme-option__swatch"
                          style={{
                            background: theme.preview.background,
                            borderColor: theme.preview.borderColor,
                            "--screen-config-theme-accent":
                              theme.preview.accentColor,
                          } as React.CSSProperties}
                          aria-hidden="true"
                        />
                        <span>{t(theme.labelKey)}</span>
                      </span>
                    ),
                    value: theme.id,
                  }))}
                />
              </Form.Item>
              <div className="screen-config-section__subsection">
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
                    type={
                      activePresetKey === "custom" ? "primary" : "default"
                    }
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
            </div>
            <div className="screen-config-section">
              <div className="screen-config-section__title">
                {t("opsAnalysis.screen.screenSettings")}
              </div>
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
              {showTitle && (
                <Form.Item
                  name="title"
                  label={t("opsAnalysis.screen.screenTitle")}
                  className="mt-4 mb-0"
                  rules={[
                    {
                      required: true,
                      whitespace: true,
                      message: t("opsAnalysis.screen.screenTitlePlaceholder"),
                    },
                  ]}
                >
                  <Input
                    maxLength={64}
                    placeholder={t(
                      "opsAnalysis.screen.screenTitlePlaceholder",
                    )}
                  />
                </Form.Item>
              )}
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
          padding-top: 4px;
        }

        .screen-config-form {
          display: flex;
          flex-direction: column;
          gap: 18px;
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
          margin-top: 12px;
        }

        .screen-config-section__subsection {
          margin-top: 16px;
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

        .screen-config-theme-option {
          display: inline-flex;
          min-width: 0;
          align-items: center;
          justify-content: center;
          gap: 8px;
          line-height: 24px;
        }

        .screen-config-theme-option__swatch {
          position: relative;
          display: inline-block;
          width: 20px;
          height: 14px;
          flex-shrink: 0;
          border: 1px solid;
          border-radius: 4px;
          overflow: hidden;
        }

        .screen-config-theme-option__swatch::after {
          content: '';
          position: absolute;
          left: 5px;
          right: 5px;
          bottom: 3px;
          height: 2px;
          border-radius: 999px;
          background: var(--screen-config-theme-accent);
        }
      `}</style>
    </>
  );
};

export default ScreenConfigModal;
