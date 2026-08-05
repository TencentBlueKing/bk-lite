"use client";

import React, { useEffect, useRef, useState } from "react";
import { Button, Drawer, List, Tag } from "antd";
import { ExportOutlined } from "@ant-design/icons";
import MarkdownRenderer from "@/components/markdown";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import { openWikiMaterialDetailInNewWindow } from "@/app/opspilot/utils/wikiMaterialRoutes";
import type {
  KnowledgePage,
  MaterialType,
  WikiPageSource,
} from "@/app/opspilot/types/wiki";
import { useTranslation } from "@/utils/i18n";
import { MATERIAL_STATUS_META, materialDisplayStatus } from "./wikiFormat";

const MATERIAL_TYPE_KEY: Record<MaterialType, string> = {
  file: "wiki.materialFile",
  text: "wiki.materialText",
  web: "wiki.materialWeb",
};

interface WikiPageSourcesDrawerProps {
  page: KnowledgePage | null;
  onClose: () => void;
}

const WikiPageSourcesDrawer: React.FC<WikiPageSourcesDrawerProps> = ({
  page,
  onClose,
}) => {
  const { t } = useTranslation();
  const { fetchPageSources } = useWikiApi();
  const fetchPageSourcesRef = useRef(fetchPageSources);
  fetchPageSourcesRef.current = fetchPageSources;
  const [loading, setLoading] = useState(false);
  const [title, setTitle] = useState("");
  const [sources, setSources] = useState<WikiPageSource[]>([]);

  useEffect(() => {
    if (!page) return;

    let active = true;
    setTitle(page.title);
    setSources([]);
    setLoading(true);
    void fetchPageSourcesRef
      .current(page.id)
      .then((result) => {
        if (!active) return;
        setTitle(result.page_title || page.title);
        setSources(result.sources || []);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [page]);

  const materialTypeLabel = (type: MaterialType) =>
    MATERIAL_TYPE_KEY[type] ? t(MATERIAL_TYPE_KEY[type]) : type;

  const openMaterialDetail = (materialId: number) => {
    if (!page) return;
    openWikiMaterialDetailInNewWindow({
      kbId: page.knowledge_base,
      materialId,
    });
  };

  const renderSource = (source: WikiPageSource) => (
    <List.Item key={source.id}>
      <div className="w-full rounded border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="mb-1 text-xs text-[var(--color-text-3)]">
              {t("wiki.sourceMaterial")}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="link"
                size="small"
                className="inline-flex h-auto max-w-full items-center gap-1 p-0 text-left font-medium text-[var(--color-text-1)]"
                onClick={() => openMaterialDetail(source.material.id)}
              >
                <span className="break-all">{source.material.name}</span>
                <ExportOutlined className="text-[10px]" />
              </Button>
              <Tag className="m-0">
                {materialTypeLabel(source.material.material_type)}
              </Tag>
              {source.material.status &&
                (() => {
                  const statusMeta =
                    MATERIAL_STATUS_META[
                      materialDisplayStatus(source.material.status)
                    ];
                  return (
                    <Tag className="m-0" color={statusMeta.color}>
                      {t(statusMeta.key)}
                    </Tag>
                  );
                })()}
            </div>
          </div>
        </div>
        {source.material_version && (
          <div className="mt-2 text-xs text-[var(--color-text-3)]">
            {t("wiki.sourceVersion")} #{source.material_version.id}
          </div>
        )}
        {typeof source.locator?.chunk_index === "number" && (
          <Tag className="mt-2">
            {t("wiki.sourceChunk")} #{source.locator.chunk_index + 1}
            {typeof source.locator.chunk_count === "number"
              ? ` / ${source.locator.chunk_count}`
              : ""}
          </Tag>
        )}
        {source.snippet && (
          <div className="mt-2">
            <div className="mb-1 text-xs text-[var(--color-text-3)]">
              {t("wiki.sourceSnippet")}
            </div>
            <div className="max-w-full overflow-x-auto text-sm text-[var(--color-text-2)]">
              <MarkdownRenderer content={source.snippet} />
            </div>
          </div>
        )}
        {source.locator_raw && (
          <div className="mt-2 break-words text-xs text-[var(--color-text-3)]">
            {source.locator_raw}
          </div>
        )}
      </div>
    </List.Item>
  );

  return (
    <Drawer
      title={`${t("wiki.pageSources")}: ${title}`}
      open={!!page}
      width="min(960px, calc(100vw - 48px))"
      onClose={onClose}
    >
      <List
        loading={loading}
        locale={{ emptyText: t("wiki.noPageSources") }}
        dataSource={sources}
        renderItem={renderSource}
      />
    </Drawer>
  );
};

export default WikiPageSourcesDrawer;
