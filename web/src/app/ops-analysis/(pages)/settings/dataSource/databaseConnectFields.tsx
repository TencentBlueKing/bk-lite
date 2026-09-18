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

interface DatabaseConnectFieldsProps {
  definitionReadOnly: boolean;
  useSharedConnection: boolean;
  connectionList: DataConnectionItem[];
  extractButton: React.ReactNode;
  onPasswordFocus: (event: React.FocusEvent<HTMLInputElement>) => void;
  onPasswordBlur: (event: React.FocusEvent<HTMLInputElement>) => void;
}

export const DatabaseConnectFields: React.FC<DatabaseConnectFieldsProps> = ({
  definitionReadOnly,
  useSharedConnection,
  connectionList,
  extractButton,
  onPasswordFocus,
  onPasswordBlur,
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
              name={["connection_overrides", "database"]}
              label={t("dataConnection.overrideDatabase")}
              className="!mb-2"
            >
              <Input disabled={definitionReadOnly} placeholder={t("dataSource.database")} />
            </Form.Item>
          </>
        ) : (
          <div className="grid grid-cols-2 gap-x-3">
            <Form.Item
              name={["connection_config", "host"]}
              label={t("dataSource.host")}
              className="!mb-2"
              rules={[{ required: true, message: t("common.inputMsg") }]}
            >
              <Input placeholder="127.0.0.1" disabled={definitionReadOnly} />
            </Form.Item>
            <Form.Item
              name={["connection_config", "port"]}
              label={t("dataSource.port")}
              className="!mb-2"
              rules={[{ required: true, message: t("common.inputMsg") }]}
            >
              <InputNumber min={1} max={65535} className="w-full" disabled={definitionReadOnly} />
            </Form.Item>
            <Form.Item
              name={["connection_config", "database"]}
              label={t("dataSource.database")}
              className="!mb-2"
              rules={[{ required: true, message: t("common.inputMsg") }]}
            >
              <Input disabled={definitionReadOnly} />
            </Form.Item>
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
                onFocus={onPasswordFocus}
                onBlur={onPasswordBlur}
                disabled={definitionReadOnly}
              />
            </Form.Item>
          </div>
        )}
        <div className="grid grid-cols-2 gap-x-3">
          <Form.Item
            name={["query_config", "table"]}
            label={t("dataSource.tableName")}
            className="!mb-2"
          >
            <Input disabled={definitionReadOnly} />
          </Form.Item>
        </div>
        <Form.Item
          name={["query_config", "sql"]}
          label={t("dataSource.sql")}
          className="!mb-2"
        >
          <Input.TextArea
            rows={3}
            placeholder="SELECT * FROM table_name"
            disabled={definitionReadOnly}
          />
        </Form.Item>
        {extractButton}
      </ConnectCard>
    </Form.Item>
  );
};
