"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button, Space, Spin, message } from "antd";
import {
  DownloadOutlined,
  PlusOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { useTranslation } from "@/utils/i18n";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import {
  KnowledgePage,
  WikiDirectoryTreeResult,
} from "@/app/opspilot/types/wiki";
import WikiDirectoryTree, { toWikiTreePages } from "./WikiDirectoryTree";
import WikiPageMoveModal from "./WikiPageMoveModal";
import WikiMarkdownImportModal from "./WikiMarkdownImportModal";
import WikiPageEditorDrawer from "./WikiPageEditorDrawer";
import WikiPageReadingPane from "./WikiPageReadingPane";
import type { WikiDirectoryQuery } from "./useWikiDirectoryQuery";

interface PageTabProps {
  kbId: number;
  directoryQuery: WikiDirectoryQuery;
}

type PageLifecycleWriteMode = "loading" | "generation" | "blocked";

const PageTab: React.FC<PageTabProps> = ({ kbId, directoryQuery }) => {
  const { t } = useTranslation();
  const {
    search: nameFilter,
    selectedPageId,
    setSearch,
    setSelectedPageId,
  } = directoryQuery;
  const {
    fetchPages,
    fetchDirectoryTree,
    movePagesToDirectory,
    exportKnowledgeBaseMarkdown,
  } = useWikiApi();

  const [treePages, setTreePages] = useState<KnowledgePage[]>([]);
  const [pagesLoading, setPagesLoading] = useState(false);
  const [directoryTreeState, setDirectoryTreeState] = useState<{
    kbId: number;
    value: WikiDirectoryTreeResult;
  } | null>(null);
  const [directoryTreeLoadState, setDirectoryTreeLoadState] = useState<
    "loading" | "ready" | "error"
  >("loading");
  const [exportingMarkdown, setExportingMarkdown] = useState(false);
  const [markdownImportOpen, setMarkdownImportOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<KnowledgePage | null>(null);
  const [movePageIds, setMovePageIds] = useState<number[]>([]);
  const [moveModalOpen, setMoveModalOpen] = useState(false);
  const [directoryMutationLoading, setDirectoryMutationLoading] =
    useState(false);

  const directoryTree =
    directoryTreeState?.kbId === kbId ? directoryTreeState.value : null;
  const directoryScopeEnabled =
    typeof directoryTree?.active_generation_id === "number" &&
    typeof directoryTree?.structure_version === "number";
  const directoryMutationReady =
    directoryScopeEnabled &&
    typeof directoryTree?.active_generation_id === "number" &&
    typeof directoryTree?.structure_version === "number";
  const pageLifecycleWriteMode: PageLifecycleWriteMode =
    directoryTreeLoadState !== "ready" || !directoryTree
      ? directoryTreeLoadState === "error"
        ? "blocked"
        : "loading"
      : directoryScopeEnabled
        ? "generation"
        : "blocked";

  const refreshDirectoryTree = async () => {
    setDirectoryTreeLoadState("loading");
    try {
      const result = await fetchDirectoryTree(kbId);
      setDirectoryTreeState({ kbId, value: result });
      setDirectoryTreeLoadState("ready");
      return result;
    } catch (error) {
      setDirectoryTreeLoadState("error");
      throw error;
    }
  };

  const loadTreePages = useCallback(async () => {
    setPagesLoading(true);
    try {
      const res = await fetchPages(kbId, {
        page: 1,
        page_size: 500,
        status: "active",
      });
      setTreePages(res.items || []);
      return res.items || [];
    } finally {
      setPagesLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    let active = true;
    setDirectoryTreeState(null);
    setDirectoryTreeLoadState("loading");
    void fetchDirectoryTree(kbId)
      .then((result) => {
        if (!active) return;
        setDirectoryTreeState({ kbId, value: result });
        setDirectoryTreeLoadState("ready");
      })
      .catch(() => {
        if (!active) return;
        setDirectoryTreeState(null);
        setDirectoryTreeLoadState("error");
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    void loadTreePages();
  }, [loadTreePages]);

  useEffect(() => {
    if (!selectedPageId || pagesLoading) return;
    const exists = treePages.some((page) => page.id === selectedPageId);
    if (!exists && treePages.length > 0) {
      setSelectedPageId(null, "replace");
    }
  }, [pagesLoading, selectedPageId, setSelectedPageId, treePages]);

  const typeOptions = useMemo(
    () =>
      Array.from(
        new Set(treePages.map((page) => page.page_type).filter(Boolean)),
      ).map((value) => ({ value })),
    [treePages],
  );

  const treePageItems = useMemo(
    () => toWikiTreePages(treePages),
    [treePages],
  );

  const openCreate = () => {
    setEditing(null);
    setEditorOpen(true);
  };

  const openEdit = (record: KnowledgePage) => {
    setEditing(record);
    setEditorOpen(true);
  };

  const handleEditorPageChanged = async (pageId?: number) => {
    const pages = await loadTreePages();
    await refreshDirectoryTree().catch(() => undefined);
    return pageId ? pages.find((page) => page.id === pageId) || null : null;
  };

  const openMovePages = (pageIds: number[]) => {
    if (!directoryMutationReady || !pageIds.length) return;
    setMovePageIds(pageIds);
    setMoveModalOpen(true);
  };

  const handleMovePages = async (targetDirectoryId: number) => {
    if (
      !directoryMutationReady ||
      !directoryTree ||
      directoryTree.active_generation_id === null ||
      directoryTree.structure_version === null
    ) {
      return;
    }
    setDirectoryMutationLoading(true);
    try {
      const result = await movePagesToDirectory(
        kbId,
        movePageIds,
        targetDirectoryId,
        directoryTree.active_generation_id,
        directoryTree.structure_version,
      );
      message.success(
        t("wiki.movePagesDone").replace("{count}", String(result.changed)),
      );
      setMoveModalOpen(false);
      setMovePageIds([]);
      await Promise.all([loadTreePages(), refreshDirectoryTree()]);
    } catch {
      await refreshDirectoryTree();
    } finally {
      setDirectoryMutationLoading(false);
    }
  };

  const handleExportMarkdown = async () => {
    setExportingMarkdown(true);
    try {
      const blob = await exportKnowledgeBaseMarkdown(kbId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `wiki-kb-${kbId}-markdown.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      message.success(t("wiki.exportMarkdownDone"));
    } catch {
      message.error(t("wiki.exportMarkdownFailed"));
    } finally {
      setExportingMarkdown(false);
    }
  };

  const handleMarkdownImportCompleted = async () => {
    setMarkdownImportOpen(false);
    await Promise.allSettled([refreshDirectoryTree(), loadTreePages()]);
  };

  return (
    <>
      <div className="flex h-full min-h-0 flex-col gap-3">
        {pageLifecycleWriteMode === "blocked" && (
          <Alert
            showIcon
            type="error"
            className="shrink-0"
            message={t("wiki.directoryWritesUnavailable")}
            description={t("wiki.directoryWritesUnavailableDesc")}
            action={
              <Button
                size="small"
                onClick={() =>
                  void refreshDirectoryTree().catch(() => undefined)
                }
              >
                {t("wiki.structureRetry")}
              </Button>
            }
          />
        )}

        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          <Space size={8} wrap>
            <Button
              icon={<UploadOutlined />}
              onClick={() => setMarkdownImportOpen(true)}
            >
              {t("wiki.importMarkdown")}
            </Button>
            <Button
              icon={<DownloadOutlined />}
              loading={exportingMarkdown}
              onClick={handleExportMarkdown}
            >
              {t("wiki.exportMarkdown")}
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={openCreate}
            >
              {t("wiki.newPage")}
            </Button>
          </Space>
        </div>

        <div className="flex min-h-0 flex-1 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)]">
          {directoryScopeEnabled && directoryTree ? (
            <WikiDirectoryTree
              directories={directoryTree.directories}
              pages={treePageItems}
              unclassifiedDirectoryId={directoryTree.unclassified_directory_id}
              selectedPageId={selectedPageId}
              search={nameFilter}
              onSearchChange={(value) => setSearch(value, "replace")}
              onSelectPage={(pageId) => setSelectedPageId(pageId)}
            />
          ) : (
            <aside className="flex w-[260px] shrink-0 items-center justify-center border-r border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 text-xs text-[var(--color-text-3)]">
              {directoryTreeLoadState === "loading" ? (
                <Spin size="small" />
              ) : (
                t("wiki.directoryWritesUnavailable")
              )}
            </aside>
          )}

          <div className="flex min-h-0 min-w-0 flex-1 flex-col p-3">
            <WikiPageReadingPane
              kbId={kbId}
              pageId={selectedPageId}
              treePages={treePageItems}
              onEdit={openEdit}
              onMove={(page) => openMovePages([page.id])}
              onOpenRelatedPage={(pageId) => setSelectedPageId(pageId)}
            />
          </div>
        </div>
      </div>

      <WikiPageMoveModal
        open={moveModalOpen}
        loading={directoryMutationLoading}
        pageCount={movePageIds.length}
        directories={directoryTree?.directories || []}
        onCancel={() => setMoveModalOpen(false)}
        onConfirm={handleMovePages}
      />

      <WikiMarkdownImportModal
        kbId={kbId}
        open={markdownImportOpen}
        directories={directoryTree?.directories || []}
        directoryEnabled={directoryScopeEnabled}
        onCancel={() => setMarkdownImportOpen(false)}
        onCompleted={handleMarkdownImportCompleted}
      />

      <WikiPageEditorDrawer
        kbId={kbId}
        open={editorOpen}
        page={editing}
        typeOptions={typeOptions}
        onClose={() => setEditorOpen(false)}
        onPageChanged={handleEditorPageChanged}
      />
    </>
  );
};

export default PageTab;
