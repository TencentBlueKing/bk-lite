"use client";

import React from "react";
import { Form, Input, InputNumber, Select } from "antd";
import { useTranslation } from "@/utils/i18n";
import { DataConnectionItem } from "@/app/ops-analysis/types/dataConnection";
import { ELASTICSEARCH_DEFAULT_QUERY_BODY } from "./operateModalUtils";
import {
  ConnectCard,
  ConnectionModeFields,
  connectionSelectOptions,
} from "./operateModalFormLayout";

interface ElasticsearchConnectFieldsProps {
  definitionReadOnly: boolean;
  useSharedConnection: boolean;
  connectionList: DataConnectionItem[];
  authType: string;
  extractButton: React.ReactNode;
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

export const ElasticsearchConnectFields: React.FC<ElasticsearchConnectFieldsProps> = ({
  definitionReadOnly,
  useSharedConnection,
  connectionList,
  authType,
  extractButton,
  onPasswordFocus,
  onPasswordBlur,
  onSecretFocus,
  onSecretBlur,
}) => {
  const { t } = useTranslation();

  return (
    <Form.Item>
      <ConnectCard>
        <ConnectionModeFields disabled={definitionReadOnly} />
        {useSharedConnection ? (
          <>
            <Form.Item
              name="connection"
              label={t("dataConnection.selectConnection")}
              className="!mb-2"
              rules={[{ required: true, message: t("common.selectMsg") }]}
            >
              <Select
                disabled={definitionReadOnly}
                placeholder={t("common.selectMsg")}
                options={connectionSelectOptions(connectionList)}
                showSearch
                optionFilterProp="label"
              />
            </Form.Item>
            <Form.Item
              name={["connection_overrides", "index"]}
              label={t("dataConnection.overrideIndex")}
              className="!mb-2"
            >
              <Input disabled={definitionReadOnly} placeholder={t("dataSource.index")} />
            </Form.Item>
          </>
        ) : (
          <div className="grid grid-cols-2 gap-x-3">
            <Form.Item
              name={["connection_config", "url"]}
              label={t("dataSource.url")}
              className="!mb-2"
              rules={[{ required: true, message: t("common.inputMsg") }]}
            >
              <Input placeholder="https://es.example.com:9200" disabled={definitionReadOnly} />
            </Form.Item>
            <Form.Item
              name={["connection_config", "index"]}
              label={t("dataSource.index")}
              className="!mb-2"
              rules={[{ required: true, message: t("common.inputMsg") }]}
            >
              <Input placeholder="logs-*" disabled={definitionReadOnly} />
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
                  { label: t("dataSource.authTypes.apiKey"), value: "api_key" },
                ]}
              />
            </Form.Item>
            <Form.Item
              name={["connection_config", "timeout_seconds"]}
              label={t("dataSource.timeout")}
              className="!mb-2"
              initialValue={30}
            >
              <InputNumber min={1} max={60} className="w-full" disabled={definitionReadOnly} />
            </Form.Item>
            {authType === "basic" && (
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
            {authType === "api_key" && (
              <Form.Item
                name={["connection_config", "api_key"]}
                label={t("dataSource.apiKey")}
                className="!mb-2"
                rules={[{ required: true, message: t("common.inputMsg") }]}
              >
                <Input.Password
                  autoComplete="new-password"
                  disabled={definitionReadOnly}
                  onFocus={(event) => onSecretFocus(["connection_config", "api_key"], event)}
                  onBlur={(event) => onSecretBlur(["connection_config", "api_key"], event)}
                />
              </Form.Item>
            )}
            <Form.Item
              name={["connection_config", "ca_cert"]}
              label={t("dataSource.caCert")}
              className="!mb-2 col-span-2"
            >
              <Input.TextArea
                rows={3}
                placeholder={"-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"}
                disabled={definitionReadOnly}
              />
            </Form.Item>
          </div>
        )}
        <Form.Item
          name={["query_config", "body"]}
          label={t("dataSource.queryDsl")}
          className="!mb-2"
          initialValue={ELASTICSEARCH_DEFAULT_QUERY_BODY}
          rules={[{ required: true, message: t("common.inputMsg") }]}
        >
          <Input.TextArea
            rows={6}
            disabled={definitionReadOnly}
          />
        </Form.Item>
        {extractButton}
      </ConnectCard>
    </Form.Item>
  );
};
