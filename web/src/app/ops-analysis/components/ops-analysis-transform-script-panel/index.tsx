"use client";

import React from "react";
import { Form, Switch, Tooltip } from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";
import CodeEditor from "@/components/code-editor";
import { useTranslation } from "@/utils/i18n";
import ConfigBlock from "@/app/ops-analysis/components/ops-analysis-config-block";

interface TransformScriptPanelProps {
  enabled: boolean;
  readOnly?: boolean;
  onEnabledChange?: (enabled: boolean) => void;
  onScriptChange?: () => void;
}

const TransformScriptPanel: React.FC<TransformScriptPanelProps> = ({
  enabled,
  readOnly = false,
  onEnabledChange,
  onScriptChange,
}) => {
  const { t } = useTranslation();

  return (
    <ConfigBlock
      className="mb-3"
      title={
        <>
          <span>{t("dataSource.transform.title")}</span>
          <Tooltip
            placement="top"
            overlayStyle={{ maxWidth: 420 }}
            overlayInnerStyle={{ maxWidth: 420 }}
            title={
              <div>
                <div className="mb-1 font-medium">
                  {t("dataSource.transform.contractTitle")}
                </div>
                <ul className="mb-0 list-disc pl-4 text-[12px] leading-5">
                  <li>{t("dataSource.transform.contractSignature")}</li>
                  <li>{t("dataSource.transform.contractModules")}</li>
                  <li>{t("dataSource.transform.contractSize")}</li>
                  <li>{t("dataSource.transform.contractLimits")}</li>
                  <li>{t("dataSource.transform.contractParams")}</li>
                </ul>
              </div>
            }
          >
            <QuestionCircleOutlined
              aria-label={t("dataSource.transform.contractTitle")}
              className="cursor-help text-[14px] text-[var(--color-text-3)]"
            />
          </Tooltip>
        </>
      }
      extra={
        <Form.Item
          name={["transform_config", "enabled"]}
          valuePropName="checked"
          getValueFromEvent={(checked: boolean) => {
            onEnabledChange?.(checked);
            return checked;
          }}
          style={{ marginBottom: 0 }}
        >
          <Switch
            disabled={readOnly}
            checkedChildren={t("dataSource.transform.enabled")}
            unCheckedChildren={t("dataSource.transform.disabled")}
          />
        </Form.Item>
      }
    >
      {enabled ? (
        <>
          <Form.Item name={["transform_config", "language"]} hidden>
            <input />
          </Form.Item>
          <Form.Item
            name={["transform_config", "script"]}
            getValueFromEvent={(value: string) => {
              onScriptChange?.();
              return value;
            }}
            rules={[
              {
                validator: async (_, value) => {
                  if (!enabled) return;
                  if (typeof value !== "string" || !value.trim()) {
                    throw new Error(t("dataSource.transform.scriptRequired"));
                  }
                },
              },
            ]}
            style={{ marginBottom: 0 }}
          >
            <CodeEditor
              mode="python"
              theme="monokai"
              width="100%"
              height="220px"
              readOnly={readOnly}
              headerOptions={{ copy: true, fullscreen: true }}
              setOptions={{ showPrintMargin: false, useWorker: false }}
            />
          </Form.Item>
        </>
      ) : null}
    </ConfigBlock>
  );
};

export default TransformScriptPanel;
