"use client";

import React from "react";
import GroupTreeSelect from "@/components/group-tree-select";
import { Form, Input, Select, Checkbox, Spin } from "antd";
import {
  ApiOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  FileExcelOutlined,
  MailOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useTranslation } from "@/utils/i18n";
import { DataSourceSourceType, DatasourceItem } from "@/app/ops-analysis/types/dataSource";
import { NamespaceItem, TagItem } from "@/app/ops-analysis/types/namespace";
import { isBuiltinDatasource } from "./operateModalUtils";

const SOURCE_TYPE_ICONS: Record<
  DataSourceSourceType,
  React.ComponentType<{ className?: string }>
> = {
  nats: MailOutlined,
  rest_api: ApiOutlined,
  postgresql: DatabaseOutlined,
  mysql: DatabaseOutlined,
  excel: FileExcelOutlined,
  prometheus: ClockCircleOutlined,
  elasticsearch: SearchOutlined,
};

interface SourceTypeCardPickerProps {
  value?: DataSourceSourceType;
  onChange?: (value: DataSourceSourceType) => void;
  onSelect?: (value: DataSourceSourceType) => void;
  options: Array<{ label: string; value: DataSourceSourceType }>;
  disabled?: boolean;
}

const SourceTypeCardPicker: React.FC<SourceTypeCardPickerProps> = ({
  value,
  onChange,
  onSelect,
  options,
  disabled = false,
}) => (
  <div className="grid grid-cols-4 gap-2">
    {options.map((option) => {
      const selected = value === option.value;
      const Icon = SOURCE_TYPE_ICONS[option.value];
      return (
        <div
          key={option.value}
          role="button"
          tabIndex={disabled ? -1 : 0}
          aria-label={option.label}
          aria-pressed={selected}
          aria-disabled={disabled}
          className={`box-border flex min-h-[48px] w-full flex-col items-center justify-center gap-0.5 rounded-lg px-1.5 py-1.5 text-xs leading-4 outline-none transition-colors duration-150 ${
            selected ? "font-medium" : "font-normal"
          } ${disabled ? "cursor-not-allowed" : "cursor-pointer"}`}
          style={{
            color: selected ? "var(--color-primary)" : "var(--color-text-2)",
            backgroundColor: selected
              ? "var(--color-primary-bg-active)"
              : "var(--color-bg-1)",
            boxShadow: selected
              ? "inset 0 0 0 1px var(--color-primary)"
              : "inset 0 0 0 1px var(--color-border-2)",
          }}
          onMouseEnter={(event) => {
            if (disabled) return;
            event.currentTarget.style.color = "var(--color-primary)";
            event.currentTarget.style.boxShadow = "inset 0 0 0 1px var(--color-primary)";
          }}
          onMouseLeave={(event) => {
            if (disabled) return;
            event.currentTarget.style.color = selected
              ? "var(--color-primary)"
              : "var(--color-text-2)";
            event.currentTarget.style.boxShadow = selected
              ? "inset 0 0 0 1px var(--color-primary)"
              : "inset 0 0 0 1px var(--color-border-2)";
          }}
          onKeyDown={(event) => {
            if (disabled || (event.key !== "Enter" && event.key !== " ")) return;
            event.preventDefault();
            if (option.value === value) return;
            onChange?.(option.value);
            onSelect?.(option.value);
          }}
          onClick={() => {
            if (disabled || option.value === value) return;
            onChange?.(option.value);
            onSelect?.(option.value);
          }}
        >
          <Icon className="text-[16px]" />
          <span className="max-w-full truncate">{option.label}</span>
        </div>
      );
    })}
  </div>
);

interface DatasourceBasicFieldsProps {
  definitionReadOnly: boolean;
  groupsReadOnly: boolean;
  currentRow?: DatasourceItem;
  sourceType?: DataSourceSourceType;
  sourceTypeLocked: boolean;
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
  sourceType,
  sourceTypeLocked,
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
  const showDetailFields = sourceTypeLocked || Boolean(sourceType);

  return (
    <>
      <Form.Item
        name="source_type"
        label={t("dataSource.sourceType")}
        rules={[{ required: true, message: t("common.selectMsg") }]}
      >
        <SourceTypeCardPicker
          options={sourceTypeOptions}
          disabled={sourceTypeLocked}
          onSelect={onSourceTypeChange}
        />
      </Form.Item>

      {showDetailFields ? (
        <>
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
                label={t("dataSource.sourceObject")}
                rules={[{ required: true, message: t("common.inputMsg") }]}
              >
                <Input
                  placeholder="alert/query_alert_center_distribution"
                  disabled={definitionReadOnly}
                />
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
      ) : null}
    </>
  );
};
