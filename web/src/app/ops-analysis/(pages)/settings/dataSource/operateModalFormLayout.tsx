"use client";

import React from "react";
import { Form, Radio } from "antd";
import { useTranslation } from "@/utils/i18n";
import { DataConnectionItem } from "@/app/ops-analysis/types/dataConnection";

export type FormSectionId = "basic" | "process";
export type FormSubsectionId = "connect" | "preview" | "fields";

export function resolveSubsectionForFieldName(
  name: string | number | (string | number)[],
): FormSubsectionId | null {
  const root = Array.isArray(name) ? name[0] : name;
  const key = String(root || "");
  if (
    key === "transform_config" ||
    key === "excel_file" ||
    key.startsWith("transform")
  ) {
    return "preview";
  }
  if (key === "field_schema" || key === "schema") {
    return "fields";
  }
  if (
    key === "connection" ||
    key === "connection_mode" ||
    key === "connection_config" ||
    key === "connection_overrides" ||
    key === "query_config" ||
    key === "params"
  ) {
    return "connect";
  }
  return null;
}

export function resolveSectionForFieldName(
  name: string | number | (string | number)[],
): FormSectionId {
  return resolveSubsectionForFieldName(name) ? "process" : "basic";
}

export function fieldDomId(name: string | number | (string | number)[]): string {
  return (Array.isArray(name) ? name : [name]).map(String).join("_");
}

export const FormSection: React.FC<{
  id: FormSectionId;
  step: number;
  title: string;
  titleExtra?: React.ReactNode;
  extra?: React.ReactNode;
  children: React.ReactNode;
}> = ({ id, step, title, titleExtra, extra, children }) => (
  <section
    id={`ds-form-section-${id}`}
    data-form-section={id}
    className="scroll-mt-3 [&:not(:last-child)]:mb-7 [&>.ant-form-item:last-child]:mb-0 [&>.ant-form-item]:mb-5"
  >
    <div className="mb-4 flex min-h-[28px] items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <div className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[var(--color-primary)] text-[11px] font-semibold text-white"
          >
            {step}
          </span>
          <h3 className="m-0 text-[13px] font-semibold leading-5 text-[var(--color-primary)]">
            {title}
          </h3>
        </div>
        {titleExtra}
      </div>
      {extra ? <div className="shrink-0">{extra}</div> : null}
    </div>
    {children}
  </section>
);

export const FormSubsection: React.FC<{
  id: FormSubsectionId;
  title: string;
  titleExtra?: React.ReactNode;
  extra?: React.ReactNode;
  children: React.ReactNode;
}> = ({ id, title, titleExtra, extra, children }) => (
  <div
    id={`ds-form-subsection-${id}`}
    data-form-subsection={id}
    className="scroll-mt-3 [&:not(:last-child)]:mb-6 [&>.ant-form-item:last-child]:mb-0 [&>.ant-form-item]:mb-5"
  >
    <div className="mb-3 flex min-h-[22px] items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-1.5">
        <h4 className="m-0 text-sm font-semibold leading-[22px] text-[var(--color-text-1)]">
          {title}
        </h4>
        {titleExtra}
      </div>
      {extra ? <div className="shrink-0">{extra}</div> : null}
    </div>
    {children}
  </div>
);

export const ConnectCard: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => (
  <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-2)] px-4 pb-1 pt-4">
    {children}
  </div>
);

export const ConnectionModeFields: React.FC<{ disabled: boolean }> = ({
  disabled,
}) => {
  const { t } = useTranslation();
  return (
    <Form.Item
      name="connection_mode"
      label={t("dataConnection.title")}
      className="!mb-2"
      initialValue="connection"
    >
      <Radio.Group disabled={disabled}>
        <Radio.Button value="connection">
          {t("dataConnection.useConnection")}
        </Radio.Button>
        <Radio.Button value="inline">
          {t("dataConnection.useInline")}
        </Radio.Button>
      </Radio.Group>
    </Form.Item>
  );
};

export function connectionSelectOptions(list: DataConnectionItem[]) {
  return list.map((item) => ({
    label: `${item.name}${item.endpoint_summary ? ` (${item.endpoint_summary})` : ""}`,
    value: item.id,
  }));
}
