"use client";

import React from "react";
import { Form, Input, InputNumber, Select } from "antd";
import { useTranslation } from "@/utils/i18n";
import { DataConnectionItem } from "@/app/ops-analysis/types/dataConnection";
import {
  ConnectCard,
  ConnectionModeFields,
  connectionSelectOptions,
} from "./operateModalFormLayout";

interface RestApiConnectFieldsProps {
  definitionReadOnly: boolean;
  useSharedConnection: boolean;
  connectionList: DataConnectionItem[];
  extractButton: React.ReactNode;
}

export const RestApiConnectFields: React.FC<RestApiConnectFieldsProps> = ({
  definitionReadOnly,
  useSharedConnection,
  connectionList,
  extractButton,
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
              name={["connection_overrides", "path"]}
              label={t("dataConnection.relativePath")}
              className="!mb-2"
            >
              <Input disabled={definitionReadOnly} placeholder="/api/v1/items" />
            </Form.Item>
          </>
        ) : (
          <Form.Item
            name={["connection_config", "url"]}
            label={t("dataSource.url")}
            className="!mb-2"
            rules={[{ required: true, message: t("common.inputMsg") }]}
          >
            <Input placeholder="https://example.com/api" disabled={definitionReadOnly} />
          </Form.Item>
        )}
        <div className="grid grid-cols-2 gap-x-3">
          <Form.Item
            name={["connection_config", "method"]}
            label={t("dataSource.method")}
            className="!mb-2"
            initialValue="GET"
          >
            <Select
              disabled={definitionReadOnly}
              options={[
                { label: "GET", value: "GET" },
                { label: "POST", value: "POST" },
              ]}
            />
          </Form.Item>
          <Form.Item
            name={["connection_config", "timeout"]}
            label={t("dataSource.timeout")}
            className="!mb-2"
            initialValue={10}
          >
            <InputNumber min={1} max={30} className="w-full" disabled={definitionReadOnly} />
          </Form.Item>
          <Form.Item
            name={["query_config", "response_path"]}
            label={t("dataSource.responsePath")}
            className="!mb-2"
          >
            <Input placeholder="data.items" disabled={definitionReadOnly} />
          </Form.Item>
        </div>
        {!useSharedConnection && (
          <Form.Item
            name={["connection_config", "headersText"]}
            label={t("dataSource.headers")}
            className="!mb-2"
          >
            <Input.TextArea
              rows={3}
              placeholder='{"Authorization":"Bearer ..."}'
              disabled={definitionReadOnly}
            />
          </Form.Item>
        )}
        <Form.Item
          name={["query_config", "paramsText"]}
          label={t("dataSource.queryParams")}
          className="!mb-2"
        >
          <Input.TextArea rows={3} placeholder='{"page":1}' disabled={definitionReadOnly} />
        </Form.Item>
        <Form.Item
          name={["query_config", "bodyText"]}
          label={t("dataSource.requestBody")}
          className="!mb-2"
        >
          <Input.TextArea rows={3} placeholder='{"limit":50}' disabled={definitionReadOnly} />
        </Form.Item>
        {extractButton}
      </ConnectCard>
    </Form.Item>
  );
};
