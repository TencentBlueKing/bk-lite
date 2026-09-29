"use client";

import React, { useCallback, useState } from "react";
import { Button, Descriptions, List, Tag, message } from "antd";
import { ArrowLeftOutlined, DownloadOutlined } from "@ant-design/icons";
import MarkdownRenderer from "@/components/markdown";
import {
  isRedundantWikiAiSummary,
  pickWikiMaterialBodyMarkdown,
} from "@/app/opspilot/utils/wikiMaterialDisplay";
import { parseJsonErrorBlob, parseExportBlobError } from "@/app/opspilot/utils/wikiExportBlobError";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import type { MaterialInfo, MaterialType } from "@/app/opspilot/types/wiki";
import { useTranslation } from "@/utils/i18n";
import { formatPageTypeLabel } from "./wikiFormat";

const MATERIAL_TYPE_KEY: Record<MaterialType, string> = {
  file: "wiki.materialFile",
  text: "wiki.materialText",
  web: "wiki.materialWeb",
};

interface MaterialDetailPanelProps {
  detail: MaterialInfo;
  onBack?: () => void;
  /** 新窗口打开时可不显示返回（可用浏览器后退/关页） */
  showBack?: boolean;
}

const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--color-text-1)]">
    <span
      className="inline-block h-4 w-1 shrink-0 rounded-sm bg-[var(--color-primary)]"
      aria-hidden
    />
    {children}
  </div>
);

const MaterialDetailPanel: React.FC<MaterialDetailPanelProps> = ({
  detail,
  onBack,
  showBack = true,
}) => {
  const { t } = useTranslation();
  const { downloadMaterialFile } = useWikiApi();
  const [downloading, setDownloading] = useState(false);
  const bodyMarkdown = pickWikiMaterialBodyMarkdown(
    detail.parsed_markdown,
    detail.ai_summary,
  );
  const showDistinctSummary = !isRedundantWikiAiSummary(
    detail.parsed_markdown,
    detail.ai_summary,
  );
  const materialTypeLabel = (type: MaterialType) =>
    MATERIAL_TYPE_KEY[type] ? t(MATERIAL_TYPE_KEY[type]) : type;

  // 经 Server 代理下载（带鉴权头），不复用 file_url 直连对象存储。
  const handleDownload = useCallback(async () => {
    if (downloading) return;
    setDownloading(true);
    try {
      const blob = await downloadMaterialFile(detail.material.id);
      const jsonError = await parseJsonErrorBlob(blob);
      if (jsonError) {
        message.error(jsonError.message);
        return;
      }
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = detail.material.name || "download";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      const parsed = await parseExportBlobError(error);
      message.error(parsed?.message || t("wiki.downloadFileFailed"));
    } finally {
      setDownloading(false);
    }
  }, [downloading, downloadMaterialFile, detail.material.id, detail.material.name, t]);

  return (
    <div className="flex h-full min-h-0 min-w-0 w-full flex-col overflow-hidden">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-components-side-nav-bg)] pb-2">
        {showBack && onBack && (
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={onBack}
            className="px-1"
          >
            {t("common.back")}
          </Button>
        )}
        <div className="min-w-0 flex-1 break-all text-base font-medium text-[var(--color-text-1)]">
          {t("wiki.detail")}: {detail.material.name}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto pt-3">
        <Descriptions
          column={1}
          bordered
          size="small"
          labelStyle={{ width: 144, whiteSpace: "nowrap" }}
          contentStyle={{ minWidth: 0 }}
        >
          <Descriptions.Item label={t("wiki.materialType")}>
            {materialTypeLabel(detail.material.material_type)}
          </Descriptions.Item>
          {detail.material.material_type === "web" && (
            <Descriptions.Item label={t("wiki.webSyncEnabled")}>
              {detail.material.sync_policy?.enabled
                ? `${t("wiki.webSyncInterval")} ${detail.material.sync_policy?.interval_hours ?? 24} ${t("wiki.hours")}`
                : "--"}
            </Descriptions.Item>
          )}
          {detail.material.material_type === "file" && (
            <Descriptions.Item label={t("wiki.imageEnhance")}>
              {detail.material.ocr_enhance ? t("common.yes") : t("common.no")}
            </Descriptions.Item>
          )}
          <Descriptions.Item label={t("wiki.original")}>
            {detail.file_url ? (
              <Button
                type="link"
                size="small"
                icon={<DownloadOutlined />}
                loading={downloading}
                onClick={handleDownload}
                className="h-auto px-0"
                style={{ color: "var(--color-primary)" }}
              >
                {t("wiki.downloadFile")}
              </Button>
            ) : (
              <span className="break-all">{detail.original || "--"}</span>
            )}
          </Descriptions.Item>
        </Descriptions>

        <section className="mt-2 border-t border-[var(--color-border-2)] pt-6">
          <SectionTitle>{t("wiki.parsedMarkdown")}</SectionTitle>
          {bodyMarkdown ? (
            <div className="min-w-0 max-w-full overflow-x-auto rounded border border-[var(--color-border-1)] p-3 text-sm">
              <MarkdownRenderer content={bodyMarkdown} />
            </div>
          ) : (
            <span className="text-[var(--color-text-3)]">--</span>
          )}
        </section>

        {showDistinctSummary && (
          <section>
            <SectionTitle>{t("wiki.aiSummary")}</SectionTitle>
            <div className="max-w-full overflow-x-auto text-xs whitespace-pre-wrap text-[var(--color-text-2)]">
              {detail.ai_summary}
            </div>
          </section>
        )}

        <section>
          <SectionTitle>{t("wiki.versions")}</SectionTitle>
          <List
            size="small"
            dataSource={detail.versions}
            locale={{ emptyText: "--" }}
            renderItem={(v) => (
              <List.Item>
                <span>#{v.id}</span>
                <span className="text-xs text-gray-400">{v.created_at}</span>
              </List.Item>
            )}
          />
        </section>
        <section>
          <SectionTitle>{t("wiki.contributedPages")}</SectionTitle>
          <List
            size="small"
            dataSource={detail.contributed_pages}
            locale={{ emptyText: "--" }}
            renderItem={(p) => (
              <List.Item>
                <span className="truncate mr-2">{p.title}</span>
                <Tag>{formatPageTypeLabel(t, p.page_type)}</Tag>
              </List.Item>
            )}
          />
        </section>
      </div>
    </div>
  );
};

export default MaterialDetailPanel;
