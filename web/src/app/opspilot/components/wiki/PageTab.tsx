"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Space, Spin, message } from "antd";
import {
  FileZipOutlined,
  ImportOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { useTranslation } from "@/utils/i18n";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import {
  KnowledgePage,
  WikiDirectoryTreeResult,
} from "@/app/opspilot/types/wiki";
import {
  parseExportBlobError,
  parseJsonErrorBlob,
} from "@/app/opspilot/utils/wikiExportBlobError";
import {
  okfImportHoldTimedOut,
  resolveOkfImportProgress,
  type OkfImportAcceptance,
} from "@/app/opspilot/utils/wikiMarkdownImport";
import WikiDirectoryTree, {
  findFirstWikiTreePageId,
  toWikiTreePages,
  type WikiTreeMaterialItem,
} from "./WikiDirectoryTree";
import WikiPageMoveModal from "./WikiPageMoveModal";
import WikiMarkdownImportModal from "./WikiMarkdownImportModal";
import WikiPageEditorDrawer from "./WikiPageEditorDrawer";
import WikiMaterialSourcePane from "./WikiMaterialSourcePane";
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
    selectedMaterialId,
    setSearch,
    setSelectedPageId,
    setSelectedMaterialId,
  } = directoryQuery;
  const {
    fetchPages,
    fetchMaterials,
    fetchDirectoryTree,
    fetchBuildRecords,
    deleteNestedDirectory,
    movePagesToDirectory,
    exportKnowledgeBaseOkf,
    deletePage,
  } = useWikiApi();

  const [treePages, setTreePages] = useState<KnowledgePage[]>([]);
  const [treeMaterials, setTreeMaterials] = useState<WikiTreeMaterialItem[]>([]);
  const [pagesLoading, setPagesLoading] = useState(false);
  const [materialsLoading, setMaterialsLoading] = useState(false);
  const [directoryTreeState, setDirectoryTreeState] = useState<{
    kbId: number;
    value: WikiDirectoryTreeResult;
  } | null>(null);
  const [directoryTreeLoadState, setDirectoryTreeLoadState] = useState<
    "loading" | "ready" | "error"
  >("loading");
  const [exportingOkf, setExportingOkf] = useState(false);
  const [okfImportOpen, setOkfImportOpen] = useState(false);
  const [okfImportProgress, setOkfImportProgress] = useState<number | null>(null);
  const [okfImportEnriching, setOkfImportEnriching] = useState(false);
  const okfImportHoldRef = useRef(false);
  const okfImportSeenRef = useRef(false);
  const okfImportTrackedIdRef = useRef<number | null>(null);
  const okfImportAcceptedStatusRef = useRef<string | null>(null);
  const okfImportHoldStartedAtRef = useRef<number | null>(null);
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
  }, [kbId]);

  const loadTreeMaterials = useCallback(async () => {
    setMaterialsLoading(true);
    try {
      const res = await fetchMaterials(kbId, {
        page: 1,
        page_size: 500,
      });
      setTreeMaterials(
        (res.items || []).map((material) => ({
          id: material.id,
          name: material.name,
        })),
      );
    } finally {
      setMaterialsLoading(false);
    }
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
  }, [kbId]);

  useEffect(() => {
    void loadTreePages();
  }, [loadTreePages]);

  useEffect(() => {
    void loadTreeMaterials();
  }, [loadTreeMaterials]);

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

  // 进入知识页且未选中时，按树序默认打开第一份页面；空目录自动跳到后续有页面的节点
  useEffect(() => {
    if (
      pagesLoading ||
      materialsLoading ||
      !directoryTree ||
      directoryTreeLoadState !== "ready"
    ) {
      return;
    }
    if (selectedMaterialId != null) {
      const materialExists = treeMaterials.some(
        (material) => material.id === selectedMaterialId,
      );
      if (materialExists) return;
      setSelectedMaterialId(null, "replace");
    }
    const firstPageId = findFirstWikiTreePageId(
      directoryTree.directories,
      treePageItems,
      directoryTree.unclassified_directory_id,
      nameFilter,
    );
    if (selectedPageId != null) {
      const exists = treePageItems.some((page) => page.id === selectedPageId);
      if (exists) return;
    }
    if (firstPageId == null) {
      if (selectedPageId != null) setSelectedPageId(null, "replace");
      return;
    }
    if (selectedPageId !== firstPageId) {
      setSelectedPageId(firstPageId, "replace");
    }
  }, [
    directoryTree,
    directoryTreeLoadState,
    materialsLoading,
    nameFilter,
    pagesLoading,
    selectedMaterialId,
    selectedPageId,
    setSelectedMaterialId,
    setSelectedPageId,
    treeMaterials,
    treePageItems,
  ]);

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

  const handleDeletePage = async (pageId: number) => {
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
      await deletePage(
        pageId,
        directoryTree.active_generation_id,
        directoryTree.structure_version,
      );
      message.success(t("wiki.deleteSuccess"));
      if (selectedPageId === pageId) setSelectedPageId(null, "replace");
      await Promise.all([loadTreePages(), refreshDirectoryTree()]);
    } finally {
      setDirectoryMutationLoading(false);
    }
  };

  const handleDeleteDirectory = async (directoryId: number) => {
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
      await deleteNestedDirectory(
        kbId,
        directoryId,
        directoryTree.active_generation_id,
        directoryTree.structure_version,
      );
      message.success(t("wiki.deleteSuccess"));
      setSelectedPageId(null, "replace");
      await Promise.all([loadTreePages(), refreshDirectoryTree()]);
    } finally {
      setDirectoryMutationLoading(false);
    }
  };

  const downloadExportBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const handleExportOkf = async () => {
    setExportingOkf(true);
    try {
      const blob = await exportKnowledgeBaseOkf(kbId);
      const jsonError = await parseJsonErrorBlob(blob);
      if (jsonError) {
        message.error(jsonError.message);
        return;
      }
      downloadExportBlob(blob, `wiki-kb-${kbId}-okf.zip`);
      message.success(t("wiki.exportOkfDone"));
    } catch (error) {
      const parsed = await parseExportBlobError(error);
      message.error(parsed?.message || t("wiki.exportOkfFailed"));
    } finally {
      setExportingOkf(false);
    }
  };

  useEffect(() => {
    okfImportHoldRef.current = false;
    okfImportSeenRef.current = false;
    okfImportTrackedIdRef.current = null;
    okfImportAcceptedStatusRef.current = null;
    okfImportHoldStartedAtRef.current = null;
    setOkfImportProgress(null);
    setOkfImportEnriching(false);
    let stopped = false;
    let timer = 0;
    const reloadVisiblePages = async () => {
      const [treeResult, pagesResult, materialsResult] = await Promise.allSettled([
        fetchDirectoryTree(kbId),
        fetchPages(kbId, { page: 1, page_size: 500, status: "active" }),
        fetchMaterials(kbId, { page: 1, page_size: 500 }),
      ]);
      if (stopped) return;
      if (treeResult.status === "fulfilled") {
        setDirectoryTreeState({ kbId, value: treeResult.value });
        setDirectoryTreeLoadState("ready");
      }
      if (pagesResult.status === "fulfilled") {
        setTreePages(pagesResult.value.items || []);
      }
      if (materialsResult.status === "fulfilled") {
        setTreeMaterials(
          (materialsResult.value.items || []).map((material) => ({
            id: material.id,
            name: material.name,
          })),
        );
      }
    };
    const tick = async () => {
      try {
        const page = await fetchBuildRecords(kbId, {
          trigger: "markdown_import",
          page_size: 5,
        });
        if (stopped) return;
        const items = page.items || [];
        const decision = resolveOkfImportProgress({
          items,
          trackedBuildRecordId: okfImportTrackedIdRef.current,
          acceptedStatus: okfImportAcceptedStatusRef.current,
          holding: okfImportHoldRef.current,
          holdStartedAt: okfImportHoldStartedAtRef.current,
          seenActive: okfImportSeenRef.current,
          now: Date.now(),
        });
        if (decision.phase === "writing" || decision.phase === "enriching") {
          okfImportSeenRef.current = true;
          okfImportHoldRef.current = false;
          okfImportAcceptedStatusRef.current = null;
          setOkfImportEnriching(decision.phase === "enriching");
          setOkfImportProgress(
            decision.phase === "writing" ? decision.progress : 99,
          );
          await reloadVisiblePages();
        } else if (decision.phase === "holding") {
          setOkfImportEnriching(false);
          setOkfImportProgress((current) => current ?? 0);
        } else if (decision.phase === "completed") {
          const failed = decision.outcome === "failed";
          okfImportHoldRef.current = false;
          okfImportSeenRef.current = false;
          okfImportTrackedIdRef.current = null;
          okfImportAcceptedStatusRef.current = null;
          okfImportHoldStartedAtRef.current = null;
          setOkfImportEnriching(false);
          setOkfImportProgress(null);
          if (failed) {
            message.error(t("wiki.okfImportFailed"));
          }
          await reloadVisiblePages();
        } else {
          setOkfImportEnriching(false);
          setOkfImportProgress(null);
        }
      } catch {
        if (
          okfImportHoldTimedOut(
            okfImportHoldStartedAtRef.current,
            Date.now(),
            okfImportHoldRef.current,
          )
        ) {
          okfImportHoldRef.current = false;
          okfImportSeenRef.current = false;
          okfImportTrackedIdRef.current = null;
          okfImportAcceptedStatusRef.current = null;
          okfImportHoldStartedAtRef.current = null;
          setOkfImportEnriching(false);
          setOkfImportProgress(null);
          message.error(t("wiki.okfImportFailed"));
        }
      } finally {
        if (!stopped) {
          const delay =
            okfImportHoldRef.current || okfImportSeenRef.current ? 5000 : 10000;
          timer = window.setTimeout(() => {
            void tick();
          }, delay);
        }
      }
    };
    void tick();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
    // 只随知识库切换重绑；刷新函数随本次渲染闭包即可
  }, [kbId]);

  const handleOkfImportCompleted = async () => {
    setOkfImportOpen(false);
    await Promise.allSettled([
      refreshDirectoryTree(),
      loadTreePages(),
      loadTreeMaterials(),
    ]);
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
              icon={<ImportOutlined />}
              disabled={okfImportProgress != null}
              onClick={() => setOkfImportOpen(true)}
            >
              {okfImportProgress != null
                ? okfImportEnriching
                  ? t("wiki.okfImportEnriching")
                  : t("wiki.okfImportProgress", undefined, {
                    progress: okfImportProgress,
                  })
                : t("wiki.importOkf")}
            </Button>
            <Button
              icon={<FileZipOutlined />}
              loading={exportingOkf}
              disabled={okfImportProgress != null}
              onClick={handleExportOkf}
            >
              {t("wiki.exportOkf")}
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
              materials={treeMaterials}
              unclassifiedDirectoryId={directoryTree.unclassified_directory_id}
              selectedPageId={selectedPageId}
              selectedMaterialId={selectedMaterialId}
              search={nameFilter}
              onSearchChange={(value) => setSearch(value, "replace")}
              onSelectPage={(pageId) => setSelectedPageId(pageId)}
              onSelectMaterial={(materialId) => setSelectedMaterialId(materialId)}
              canMutate={
                directoryMutationReady && !directoryMutationLoading
              }
              onDeletePage={(pageId) => void handleDeletePage(pageId)}
              onDeleteDirectory={(directoryId) =>
                void handleDeleteDirectory(directoryId)
              }
              importProgress={okfImportProgress}
              importProgressLabel={
                okfImportEnriching ? t("wiki.okfImportEnriching") : null
              }
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
            {selectedMaterialId != null ? (
              <WikiMaterialSourcePane materialId={selectedMaterialId} />
            ) : (
              <WikiPageReadingPane
                kbId={kbId}
                pageId={selectedPageId}
                treePages={treePageItems}
                onEdit={openEdit}
                onMove={(page) => openMovePages([page.id])}
                onDelete={(page) => void handleDeletePage(page.id)}
                canMutate={directoryMutationReady && !directoryMutationLoading}
                onOpenRelatedPage={(pageId) => setSelectedPageId(pageId)}
              />
            )}
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
        open={okfImportOpen}
        onCancel={() => setOkfImportOpen(false)}
        onCompleted={handleOkfImportCompleted}
        onImportHoldChange={(holding, acceptance?: OkfImportAcceptance) => {
          okfImportHoldRef.current = holding;
          if (holding) {
            if (okfImportHoldStartedAtRef.current == null) {
              okfImportHoldStartedAtRef.current = Date.now();
            }
            if (typeof acceptance?.buildRecordId === "number") {
              okfImportTrackedIdRef.current = acceptance.buildRecordId;
            }
            if (acceptance?.status) {
              okfImportAcceptedStatusRef.current = acceptance.status;
            }
            setOkfImportProgress((current) => current ?? 0);
            return;
          }
          okfImportHoldStartedAtRef.current = null;
          okfImportTrackedIdRef.current = null;
          okfImportAcceptedStatusRef.current = null;
          if (!okfImportSeenRef.current) {
            setOkfImportEnriching(false);
            setOkfImportProgress(null);
          }
        }}
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
