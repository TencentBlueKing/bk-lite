"use client";

import React from "react";
import GroupTreeSelect from "@/components/group-tree-select";
import { Form, Input, Radio, Select, Checkbox, Spin } from "antd";
import { useTranslation } from "@/utils/i18n";
import { DataSourceSourceType, DatasourceItem } from "@/app/ops-analysis/types/dataSource";
import { NamespaceItem, TagItem } from "@/app/ops-analysis/types/namespace";
import { isBuiltinDatasource } from "./operateModalUtils";

interface DatasourceBasicFieldsProps {
  definitionReadOnly: boolean;
  groupsReadOnly: boolean;
  currentRow?: DatasourceItem;
  sourceTypeOptions: Array<{ label: string; value: DataSourceSourceType }>;
  chartTypeOptions: Array<{ label: string; value: string }>;
  isNatsSource: boolean;
  namespacesLoading: boolean;
  namespaceList: NamespaceItem[];
  tagsLoading: boolean;
  tagList: TagItem[];
  onSourceTypeChange: (nextSourceType: DataSourceSourceType) => void;
}

export const DatasourceBasicFields: React.FC<DatasourceBasicFieldsProps> = ({
  definitionReadOnly,
  groupsReadOnly,
  currentRow,
  sourceTypeOptions,
  chartTypeOptions,
  isNatsSource,
  namespacesLoading,
  namespaceList,
  tagsLoading,
  tagList,
  onSourceTypeChange,
}) => {
  const { t } = useTranslation();

  return (
    <>
      <Form.Item
        name="source_type"
        label={t("dataSource.sourceType")}
        rules={[{ required: true, message: t("common.inputMsg") }]}
      >
        <Radio.Group
          optionType="button"
          buttonStyle="solid"
          options={sourceTypeOptions}
          disabled={definitionReadOnly}
          onChange={(event) => {
            onSourceTypeChange(event.target.value as DataSourceSourceType);
          }}
        />
      </Form.Item>

      <Form.Item
        name="name"
        label={t("dataSource.name")}
        rules={[{ required: true, message: t("common.inputMsg") }]}
      >
        <Input placeholder={t("common.inputMsg")} disabled={definitionReadOnly} />
      </Form.Item>
      {isNatsSource && (
        <>
          <Form.Item
            name="rest_api"
            label="NATS"
            rules={[{ required: true, message: t("common.inputMsg") }]}
          >
            <Input placeholder={t("common.inputMsg")} disabled={definitionReadOnly} />
          </Form.Item>
          <Form.Item
            name="namespaces"
            label={t("namespace.title")}
            rules={[
              {
                required: true,
                type: "array",
                min: 1,
                message: t("common.selectMsg"),
              },
            ]}
          >
            {namespacesLoading ? (
              <div className="py-2 text-center">
                <Spin size="small" />
              </div>
            ) : namespaceList.length === 0 ? (
              <div className="text-[13px] text-[var(--color-text-4)]">
                {t("common.noData")}
              </div>
            ) : (
              <Checkbox.Group
                className="flex flex-wrap gap-x-4 gap-y-2 pt-1"
                disabled={definitionReadOnly}
              >
                {namespaceList.map((ns: NamespaceItem) => (
                  <Checkbox
                    key={ns.id}
                    value={ns.id}
                    className="!ml-0 flex min-w-0 items-center"
                  >
                    <span
                      className="inline-block max-w-[180px] truncate align-bottom"
                      title={ns.name}
                    >
                      {ns.name}
                    </span>
                  </Checkbox>
                ))}
              </Checkbox.Group>
            )}
          </Form.Item>
        </>
      )}
      <Form.Item
        name="tag"
        label={t("dataSource.tag")}
        rules={[
          {
            required: true,
            type: "array",
            min: 1,
            message: t("common.selectMsg"),
          },
        ]}
      >
        {tagsLoading ? (
          <div className="py-2 text-center">
            <Spin size="small" />
          </div>
        ) : tagList.length === 0 ? (
          <div className="text-[13px] text-[var(--color-text-4)]">
            {t("common.noData")}
          </div>
        ) : (
          <Checkbox.Group
            disabled={definitionReadOnly}
            options={tagList.map((tag: TagItem) => ({
              label: tag.name,
              value: tag.id,
            }))}
          />
        )}
      </Form.Item>
      <Form.Item
        name="chart_type"
        label={t("dataSource.chartType")}
        rules={[
          {
            required: true,
            type: "array",
            min: 1,
            message: t("common.selectMsg"),
          },
        ]}
      >
        <Select
          mode="multiple"
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder={t("common.selectMsg")}
          options={chartTypeOptions}
          disabled={definitionReadOnly}
        />
      </Form.Item>
      <Form.Item
        name="groups"
        label={t("common.group")}
        extra={
          isBuiltinDatasource(currentRow)
            ? t("dataSource.emptyGroupsMeansAllOrgs")
            : undefined
        }
        rules={
          isBuiltinDatasource(currentRow)
            ? undefined
            : [
              {
                required: true,
                message: `${t("common.selectMsg")}${t("common.group")}`,
              },
            ]
        }
      >
        <GroupTreeSelect
          placeholder={`${t("common.selectMsg")}${t("common.group")}`}
          multiple={true}
          mode="ownership"
          disabled={groupsReadOnly}
        />
      </Form.Item>
      <Form.Item name="desc" label={t("dataSource.describe")}>
        <Input.TextArea
          rows={3}
          disabled={definitionReadOnly}
          placeholder={`${t("common.inputMsg")} ${t("dataSource.describe")}`}
        />
      </Form.Item>
    </>
  );
};
