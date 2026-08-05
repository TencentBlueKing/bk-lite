"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Button,
  Drawer,
  Empty,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from "antd";
import {
  EditOutlined,
  ExportOutlined,
  FolderOpenOutlined,
} from "@ant-design/icons";
import MarkdownRenderer from "@/components/markdown";
import { useTranslation } from "@/utils/i18n";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import { openWikiMaterialDetailInNewWindow } from "@/app/opspilot/utils/wikiMaterialRoutes";
import type {
  GraphEdge,
  GraphNode,
  KnowledgePage,
  WikiPageSource,
} from "@/app/opspilot/types/wiki";

const WIKILINK_RE = /\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]/g;

interface RelatedPageItem {
  id: number;
  title: string;
  page_type?: string;
}

interface WikiPageReadingPaneProps {
  kbId: number;
  pageId: number | null;
  treePages: Array<{ id: number; title: string; page_type: string }>;
  onEdit: (page: KnowledgePage) => void;
  onMove: (page: KnowledgePage) => void;
  onOpenRelatedPage: (pageId: number) => void;
}

const WikiPageReadingPane: React.FC<WikiPageReadingPaneProps> = ({
  kbId,
  pageId,
  treePages,
  onEdit,
  onMove,
  onOpenRelatedPage,
}) => {
  const { t } = useTranslation();
  const { fetchPage, fetchPageSources, fetchGraph } = useWikiApi();
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState<KnowledgePage | null>(null);
  const [sources, setSources] = useState<WikiPageSource[]>([]);
  const [related, setRelated] = useState<RelatedPageItem[]>([]);
  const [drawerRelated, setDrawerRelated] = useState<RelatedPageItem | null>(
    null,
  );

  useEffect(() => {
    if (!pageId) {
      setPage(null);
      setSources([]);
      setRelated([]);
      return;
    }

    let active = true;
    setLoading(true);
    setDrawerRelated(null);

    const titleIndex = new Map(
      treePages.map((item) => [item.title.trim().toLowerCase(), item]),
    );

    void Promise.all([
      fetchPage(pageId),
      fetchPageSources(pageId).catch(() => ({
        page_id: pageId,
        page_title: "",
        sources: [] as WikiPageSource[],
      })),
      fetchGraph(kbId).catch(() => ({ nodes: [], edges: [] })),
    ])
      .then(([pageDetail, sourceResult, graph]) => {
        if (!active) return;
        setPage(pageDetail);
        setSources(sourceResult.sources || []);

        const relatedMap = new Map<number, RelatedPageItem>();
        const body = pageDetail.body || "";
        let match: RegExpExecArray | null;
        WIKILINK_RE.lastIndex = 0;
        while ((match = WIKILINK_RE.exec(body)) !== null) {
          const title = match[1]?.trim();
          if (!title) continue;
          const hit = titleIndex.get(title.toLowerCase());
          if (hit && hit.id !== pageId) {
            relatedMap.set(hit.id, {
              id: hit.id,
              title: hit.title,
              page_type: hit.page_type,
            });
          }
        }

        const nodeById = new Map<number, GraphNode>(
          (graph.nodes || []).map((node) => [node.id, node]),
        );
        (graph.edges || []).forEach((edge: GraphEdge) => {
          const otherId =
            edge.from === pageId
              ? edge.to
              : edge.to === pageId
                ? edge.from
                : null;
          if (!otherId || otherId === pageId) return;
          const node = nodeById.get(otherId);
          if (!node) return;
          relatedMap.set(otherId, {
            id: otherId,
            title: node.title,
            page_type: node.page_type,
          });
        });

        setRelated(Array.from(relatedMap.values()));
      })
      .catch(() => {
        if (active) message.error(t("common.error"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
    // treePages 仅用于解析标题索引；以 pageId/kbId 为刷新主因，避免列表引用抖动反复请求。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, pageId]);

  const openSourceInNewWindow = (source: WikiPageSource) => {
    openWikiMaterialDetailInNewWindow({
      kbId,
      materialId: source.material.id,
    });
  };

  const openRelatedDrawer = (item: RelatedPageItem) => {
    setDrawerRelated(item);
  };

  const breadcrumb = useMemo(() => {
    if (!page?.directory_breadcrumb?.length) return null;
    return page.directory_breadcrumb.map((item) => item.name).join(" / ");
  }, [page]);

  if (!pageId) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center rounded-lg border border-dashed border-[var(--color-border-1)] bg-[var(--color-bg-1)]">
        <Empty description={t("wiki.selectPageToRead")} />
      </div>
    );
  }

  // 首次加载尚无页面正文时，Spin 没有内容高度会贴顶并被 overflow 裁切，改为整区居中。
  if (loading && !page) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)]">
        <Spin />
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)]">
      <Spin
        spinning={loading}
        wrapperClassName="flex h-full min-h-0 flex-col [&_.ant-spin-container]:flex [&_.ant-spin-container]:h-full [&_.ant-spin-container]:min-h-0 [&_.ant-spin-container]:flex-col"
      >
        {page ? (
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                {breadcrumb && (
                  <div className="mb-1 text-xs text-[var(--color-text-3)]">
                    {breadcrumb}
                  </div>
                )}
              </div>
              <Space size={8} wrap>
                <Button
                  size="small"
                  icon={<FolderOpenOutlined />}
                  onClick={() => onMove(page)}
                >
                  {t("wiki.movePages")}
                </Button>
                <Button
                  size="small"
                  type="primary"
                  icon={<EditOutlined />}
                  onClick={() => onEdit(page)}
                >
                  {t("common.edit")}
                </Button>
              </Space>
            </div>

            <div className="mb-4 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Typography.Title level={4} className="!mb-0 !text-base">
                  {page.title}
                </Typography.Title>
                <Tag color="blue">{page.page_type || "--"}</Tag>
                {page.updated_at && (
                  <span className="text-xs text-[var(--color-text-3)]">
                    {page.updated_at}
                  </span>
                )}
                {(page.tags || []).map((tag) => (
                  <Tag key={tag}>{tag}</Tag>
                ))}
              </div>

              <div className="mb-3">
                <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">
                  {t("wiki.pageSources")} ({sources.length})
                </div>
                <div className="flex flex-wrap gap-2">
                  {sources.length ? (
                    sources.map((source) => (
                      <Button
                        key={source.id}
                        size="small"
                        className="inline-flex items-center gap-1"
                        onClick={() => openSourceInNewWindow(source)}
                      >
                        {source.material.name}
                        <ExportOutlined className="text-[10px]" />
                      </Button>
                    ))
                  ) : (
                    <span className="text-xs text-[var(--color-text-4)]">
                      {t("wiki.noPageSources")}
                    </span>
                  )}
                </div>
              </div>

              <div>
                <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">
                  {t("wiki.related")} ({related.length})
                </div>
                <div className="flex flex-wrap gap-2">
                  {related.length ? (
                    related.map((item) => (
                      <Button
                        key={item.id}
                        size="small"
                        className="inline-flex items-center gap-1"
                        onClick={() => openRelatedDrawer(item)}
                      >
                        {item.title}
                        <ExportOutlined className="text-[10px]" />
                      </Button>
                    ))
                  ) : (
                    <span className="text-xs text-[var(--color-text-4)]">
                      {t("wiki.noRelatedPages")}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {page.body ? (
              <div className="max-w-full overflow-x-auto text-sm">
                <MarkdownRenderer content={page.body} />
              </div>
            ) : (
              <Empty description={t("wiki.noPageBody")} />
            )}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <Empty description={t("wiki.pageNotFound")} />
          </div>
        )}
      </Spin>

      <Drawer
        open={!!drawerRelated}
        width={360}
        title={t("wiki.related")}
        onClose={() => setDrawerRelated(null)}
        destroyOnHidden
        styles={{
          body: {
            paddingTop: 12,
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
          },
        }}
      >
        {drawerRelated && (
          <div className="space-y-3">
            <div>
              <div className="mb-1 text-xs text-[var(--color-text-3)]">
                {t("wiki.related")}
              </div>
              <div className="text-sm font-medium text-[var(--color-text-1)]">
                {drawerRelated.title}
              </div>
              {drawerRelated.page_type && (
                <Tag className="mt-2">{drawerRelated.page_type}</Tag>
              )}
            </div>
            <Button
              type="primary"
              block
              onClick={() => {
                onOpenRelatedPage(drawerRelated.id);
                setDrawerRelated(null);
              }}
            >
              {t("wiki.openRelatedPage")}
            </Button>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default WikiPageReadingPane;
