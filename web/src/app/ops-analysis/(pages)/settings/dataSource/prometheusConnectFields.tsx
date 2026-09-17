"use client";

import React from "react";
import { Form, Input, InputNumber, Select, Button, Collapse } from "antd";
import { useTranslation } from "@/utils/i18n";
import { ConnectCard } from "./operateModalFormLayout";

interface PrometheusConnectFieldsProps {
  definitionReadOnly: boolean;
  prometheusAuthType: string;
  prometheusQueryType: string;
  testConnectionLoading: boolean;
  onTestConnection: () => void;
  onPasswordFocus: (event: React.FocusEvent<HTMLInputElement>) => void;
  onPasswordBlur: (event: React.FocusEvent<HTMLInputElement>) => void;
  onSecretFocus: (
    fieldPath: (string | number)[],
    event: React.FocusEvent<HTMLInputElement>,
  ) => void;
  onSecretBlur: (
    fieldPath: (string | number)[],
    event: React.FocusEvent<HTMLInputElement>,
  ) => void;
}

export const PrometheusConnectFields: React.FC<PrometheusConnectFieldsProps> = ({
  definitionReadOnly,
  prometheusAuthType,
  prometheusQueryType,
  testConnectionLoading,
  onTestConnection,
  onPasswordFocus,
  onPasswordBlur,
  onSecretFocus,
  onSecretBlur,
}) => {
  const { t } = useTranslation();

  return (
    <Form.Item>
      <ConnectCard>
        <div className="grid grid-cols-2 gap-x-3">
          <Form.Item
            name={["connection_config", "url"]}
            label={t("dataSource.url")}
            className="!mb-2"
            rules={[{ required: true, message: t("common.inputMsg") }]}
          >
            <Input placeholder="https://prometheus.example.com" disabled={definitionReadOnly} />
          </Form.Item>
          <Form.Item
            name={["connection_config", "auth_type"]}
            label={t("dataSource.authType")}
            className="!mb-2"
            initialValue="none"
          >
            <Select
              disabled={definitionReadOnly}
              options={[
                { label: t("dataSource.authTypes.none"), value: "none" },
                { label: t("dataSource.authTypes.basic"), value: "basic" },
                { label: t("dataSource.authTypes.bearer"), value: "bearer" },
              ]}
            />
          </Form.Item>
          {prometheusAuthType === "basic" && (
            <>
              <Form.Item
                name={["connection_config", "username"]}
                label={t("dataSource.username")}
                className="!mb-2"
                rules={[{ required: true, message: t("common.inputMsg") }]}
              >
                <Input disabled={definitionReadOnly} />
              </Form.Item>
              <Form.Item
                name={["connection_config", "password"]}
                label={t("dataSource.password")}
                className="!mb-2"
                rules={[{ required: true, message: t("common.inputMsg") }]}
              >
                <Input.Password
                  autoComplete="new-password"
                  disabled={definitionReadOnly}
                  onFocus={onPasswordFocus}
                  onBlur={onPasswordBlur}
                />
              </Form.Item>
            </>
          )}
          {prometheusAuthType === "bearer" && (
            <Form.Item
              name={["connection_config", "token"]}
              label={t("dataSource.token")}
              className="!mb-2"
              rules={[{ required: true, message: t("common.inputMsg") }]}
            >
              <Input.Password
                autoComplete="new-password"
                disabled={definitionReadOnly}
                onFocus={(event) => onSecretFocus(["connection_config", "token"], event)}
                onBlur={(event) => onSecretBlur(["connection_config", "token"], event)}
              />
            </Form.Item>
          )}
          <Form.Item
            name={["connection_config", "timeout_seconds"]}
            label={t("dataSource.timeout")}
            className="!mb-2"
            initialValue={30}
          >
            <InputNumber min={1} max={120} className="w-full" disabled={definitionReadOnly} />
          </Form.Item>
        </div>
        {definitionReadOnly ? null : (
          <div className="mb-3 text-right">
            <Button
              size="small"
              loading={testConnectionLoading}
              onClick={onTestConnection}
            >
              {t("dataSource.testConnection")}
            </Button>
          </div>
        )}
        <Collapse
          ghost
          items={[
            {
              key: "prometheus-preview-query",
              label: t("dataSource.prometheusPreviewQuery"),
              children: (
                <div className="grid grid-cols-2 gap-x-3">
                  <Form.Item
                    name={["query_config", "query"]}
                    label={t("dataSource.promql")}
                    className="!mb-2 col-span-2"
                    rules={[{ required: true, message: t("common.inputMsg") }]}
                  >
                    <Input.TextArea
                      rows={2}
                      placeholder="up"
                      disabled={definitionReadOnly}
                    />
                  </Form.Item>
                  <Form.Item
                    name={["query_config", "query_type"]}
                    label={t("dataSource.queryType")}
                    className="!mb-2"
                    initialValue="range"
                  >
                    <Select
                      disabled={definitionReadOnly}
                      options={[
                        { label: "range", value: "range" },
                        { label: "instant", value: "instant" },
                      ]}
                    />
                  </Form.Item>
                  {prometheusQueryType === "range" && (
                    <>
                      <Form.Item
                        name={["query_config", "time_range"]}
                        label={t("dataSource.paramTypes.timeRange")}
                        className="!mb-2"
                        initialValue={60}
                        rules={[{ required: true, message: t("common.inputMsg") }]}
                      >
                        <InputNumber
                          min={1}
                          max={44640}
                          className="w-full"
                          disabled={definitionReadOnly}
                        />
                      </Form.Item>
                      <Form.Item
                        name={["query_config", "step"]}
                        label={t("dataSource.step")}
                        className="!mb-2"
                        initialValue="1m"
                      >
                        <Input placeholder="1m" disabled={definitionReadOnly} />
                      </Form.Item>
                    </>
                  )}
                  <Form.Item
                    name={["query_config", "max_series"]}
                    label={t("dataSource.maxSeries")}
                    className="!mb-2"
                    initialValue={20}
                  >
                    <InputNumber
                      min={1}
                      max={50}
                      className="w-full"
                      disabled={definitionReadOnly}
                    />
                  </Form.Item>
                </div>
              ),
            },
          ]}
        />
      </ConnectCard>
    </Form.Item>
  );
};
