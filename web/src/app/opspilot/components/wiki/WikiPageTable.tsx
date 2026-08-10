"use client";

import React from "react";
import { Button, Popconfirm, Space, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import CustomTable from "@/components/custom-table";
import PermissionWrapper from "@/components/permission";
import type { KnowledgePage } from "@/app/opspilot/types/wiki";
import { useTranslation } from "@/utils/i18n";

import { PAGE_STATUS_LABEL } from "./wikiFormat";

const PAGE_STATUS_COLOR: Record<string, string> = {
  active: "green",
  archived: "default",
  source_invalid: "red",
};
const SHOW_PAGE_REINDEX_ACTION = false;

const formatUpdatedAt = (value?: string): string => {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
};

export interface WikiPageTableActions {
  view: (page: KnowledgePage) => void;
  edit: (page: KnowledgePage) => void;
  showSources: (page: KnowledgePage) => void;
  restoreArchive: (page: KnowledgePage) => void | Promise<void>;
  archive: (pageId: number) => void | Promise<void>;
  move: (pageIds: number[]) => void;
  reindex: (page: KnowledgePage) => void | Promise<void>;
}

interface WikiPageTableProps {
  pages: KnowledgePage[];
  unclassifiedDirectoryId: number | null;
  loading: boolean;
  selectedRowKeys: React.Key[];
  onSelectionChange: (keys: React.Key[]) => void;
  currentPage: number;
  pageSize: number;
  total: number;
  onPaginationChange: (page: number, pageSize: number) => void;
  directoryMutationReady: boolean;
  directoryMutationLoading: boolean;
  pageLifecycleMutationAllowed: boolean;
  reindexingPageId: number | null;
  actions: WikiPageTableActions;
}

const WikiPageTable: React.FC<WikiPageTableProps> = ({
  pages,
  unclassifiedDirectoryId,
  loading,
  selectedRowKeys,
  onSelectionChange,
  currentPage,
  pageSize,
  total,
  onPaginationChange,
  directoryMutationReady,
  directoryMutationLoading,
  pageLifecycleMutationAllowed,
  reindexingPageId,
  actions,
}) => {
  const { t } = useTranslation();
  const directoryPath = (page: KnowledgePage): string =>
    (page.directory_breadcrumb || [])
      .map((item) =>
        item.id === unclassifiedDirectoryId
          ? t("wiki.directoryUnclassified")
          : item.name,
      )
      .join(" / ");

  const columns: ColumnsType<KnowledgePage> = [
    { title: t("wiki.name"), dataIndex: "title", key: "title" },
    {
      title: t("wiki.type"),
      dataIndex: "page_type",
      key: "page_type",
      width: 120,
    },
    {
      title: t("wiki.directory"),
      dataIndex: "directory",
      key: "directory",
      width: 200,
      render: (_directory: number | null, page) => {
        const path = directoryPath(page);
        return (
          <span className="block truncate" title={path || undefined}>
            {path || "-"}
          </span>
        );
      },
    },
    {
      title: t("wiki.sourceSummary"),
      key: "source",
      width: 260,
      render: (_: unknown, page) => (
        <span
          className="block truncate text-xs text-[var(--color-text-3)]"
          title={page.source_summary || undefined}
        >
          {page.source_summary || "-"}
        </span>
      ),
    },
    {
      title: t("wiki.status"),
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (status: string) => (
        <Tag color={PAGE_STATUS_COLOR[status] || "default"}>
          {PAGE_STATUS_LABEL[status] ? t(PAGE_STATUS_LABEL[status]) : status}
        </Tag>
      ),
    },
    {
      title: t("wiki.updatedAt"),
      dataIndex: "updated_at",
      key: "updated_at",
      width: 168,
      render: (value?: string) => (
        <span className="whitespace-nowrap text-xs">
          {formatUpdatedAt(value)}
        </span>
      ),
    },
    {
      title: t("common.actions"),
      key: "action",
      width: 440,
      render: (_: unknown, page) =>
        page.status === "archived" ? (
          <Space>
            <Button type="link" size="small" onClick={() => actions.view(page)}>
              {t("wiki.viewPage")}
            </Button>
            <Button
              type="link"
              size="small"
              onClick={() => actions.showSources(page)}
            >
              {t("wiki.pageSources")}
            </Button>
            <Popconfirm
              title={t("wiki.restoreArchiveConfirm")}
              disabled={!pageLifecycleMutationAllowed}
              onConfirm={() => actions.restoreArchive(page)}
            >
              <Button
                type="link"
                size="small"
                disabled={!pageLifecycleMutationAllowed}
              >
                {t("wiki.restoreArchive")}
              </Button>
            </Popconfirm>
            <Popconfirm
              title={t("wiki.deleteConfirm")}
              disabled={!pageLifecycleMutationAllowed}
              onConfirm={() => actions.archive(page.id)}
            >
              <Button
                type="link"
                size="small"
                danger
                disabled={!pageLifecycleMutationAllowed}
              >
                {t("common.delete")}
              </Button>
            </Popconfirm>
          </Space>
        ) : (
          <Space>
            <PermissionWrapper requiredPermissions={["Edit"]}>
              <Button
                type="link"
                size="small"
                disabled={!directoryMutationReady || directoryMutationLoading}
                onClick={() => actions.move([page.id])}
              >
                {t("wiki.movePage")}
              </Button>
            </PermissionWrapper>
            <Button type="link" size="small" onClick={() => actions.edit(page)}>
              {t("common.edit")}
            </Button>
            <Button
              type="link"
              size="small"
              onClick={() => actions.showSources(page)}
            >
              {t("wiki.pageSources")}
            </Button>
            {SHOW_PAGE_REINDEX_ACTION && page.status === "active" && (
              <Button
                type="link"
                size="small"
                loading={reindexingPageId === page.id}
                disabled={
                  reindexingPageId !== null && reindexingPageId !== page.id
                }
                onClick={() => actions.reindex(page)}
              >
                {t("wiki.reindexPage")}
              </Button>
            )}
            <Popconfirm
              title={t("wiki.deleteConfirm")}
              disabled={!pageLifecycleMutationAllowed}
              onConfirm={() => actions.archive(page.id)}
            >
              <Button
                type="link"
                size="small"
                danger
                disabled={!pageLifecycleMutationAllowed}
              >
                {t("common.delete")}
              </Button>
            </Popconfirm>
          </Space>
        ),
    },
  ];

  return (
    <CustomTable<KnowledgePage>
      rowKey="id"
      loading={loading}
      columns={columns}
      dataSource={pages}
      rowSelection={{
        selectedRowKeys,
        onChange: onSelectionChange,
      }}
      pagination={{
        current: currentPage,
        pageSize,
        total,
        showSizeChanger: true,
        onChange: onPaginationChange,
      }}
      scroll={{ x: 1200 }}
    />
  );
};

export default WikiPageTable;
