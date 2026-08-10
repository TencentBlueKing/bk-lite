"use client";

import React, { useMemo, useState } from "react";
import { Input, Tooltip, Tree } from "antd";
import type { DataNode as TreeDataNode } from "antd/lib/tree";
import { useTranslation } from "@/utils/i18n";
import type {
  KnowledgePage,
  WikiDirectoryNode,
} from "@/app/opspilot/types/wiki";

const directoryKey = (id: number) => `directory:${id}`;
const pageKey = (id: number) => `page:${id}`;

export interface WikiTreePageItem {
  id: number;
  title: string;
  page_type: string;
  directory: number | null;
}

interface WikiDirectoryTreeProps {
  directories: WikiDirectoryNode[];
  pages: WikiTreePageItem[];
  unclassifiedDirectoryId: number | null;
  selectedPageId: number | null;
  search: string;
  onSearchChange: (value: string) => void;
  onSelectPage: (pageId: number) => void;
}

const WikiDirectoryTree: React.FC<WikiDirectoryTreeProps> = ({
  directories,
  pages,
  unclassifiedDirectoryId,
  selectedPageId,
  search,
  onSearchChange,
  onSelectPage,
}) => {
  const { t } = useTranslation();
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);

  const pagesByDirectory = useMemo(() => {
    const map = new Map<number | null, WikiTreePageItem[]>();
    const keyword = search.trim().toLowerCase();
    pages.forEach((page) => {
      if (keyword && !page.title.toLowerCase().includes(keyword)) return;
      const key = page.directory ?? null;
      const list = map.get(key) || [];
      list.push(page);
      map.set(key, list);
    });
    map.forEach((list, key) => {
      map.set(
        key,
        [...list].sort((a, b) => a.title.localeCompare(b.title, "zh")),
      );
    });
    return map;
  }, [pages, search]);

  const treeData = useMemo<TreeDataNode[]>(() => {
    const compareDirectories = (
      left: WikiDirectoryNode,
      right: WikiDirectoryNode,
    ) => {
      if (left.id === unclassifiedDirectoryId) return -1;
      if (right.id === unclassifiedDirectoryId) return 1;
      return left.order - right.order || left.name.localeCompare(right.name);
    };

    const toPageNode = (page: WikiTreePageItem): TreeDataNode => ({
      key: pageKey(page.id),
      isLeaf: true,
      title: (
        <Tooltip title={page.page_type || page.title} placement="right">
          <span className="block truncate text-[13px] leading-5">
            {page.title}
          </span>
        </Tooltip>
      ),
    });

    const toTreeNode = (directory: WikiDirectoryNode): TreeDataNode => {
      const isUnclassified = directory.id === unclassifiedDirectoryId;
      const label = isUnclassified
        ? t("wiki.directoryUnclassified")
        : directory.name;
      const childDirectories = [...(directory.children || [])].sort(
        compareDirectories,
      );
      const childPages = pagesByDirectory.get(directory.id) || [];

      return {
        key: directoryKey(directory.id),
        selectable: false,
        title: (
          <Tooltip
            title={
              isUnclassified
                ? t("wiki.directoryUnclassifiedTip")
                : directory.description || label
            }
            placement="right"
          >
            <span className="block truncate text-[13px] font-medium leading-5 text-[var(--color-text-1)]">
              {label}
            </span>
          </Tooltip>
        ),
        children: [
          ...childDirectories.map(toTreeNode),
          ...childPages.map(toPageNode),
        ],
      };
    };

    const orphanPages = pagesByDirectory.get(null) || [];
    // 不再包一层「全部知识」：当前交互只选页面，该虚拟节点不可点、无筛选效果，徒增缩进
    return [
      ...[...directories].sort(compareDirectories).map(toTreeNode),
      ...orphanPages.map(toPageNode),
    ];
  }, [directories, pagesByDirectory, t, unclassifiedDirectoryId]);

  const defaultExpanded = useMemo(() => {
    const keys: React.Key[] = [];
    const walk = (nodes: WikiDirectoryNode[]) => {
      nodes.forEach((node) => {
        keys.push(directoryKey(node.id));
        walk(node.children || []);
      });
    };
    walk(directories);
    return keys;
  }, [directories]);

  const effectiveExpandedKeys =
    expandedKeys.length > 0 ? expandedKeys : defaultExpanded;

  const selectedKeys =
    selectedPageId !== null ? [pageKey(selectedPageId)] : [];

  return (
    <aside className="flex h-full w-[260px] shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-bg-1)]">
      <div className="border-b border-[var(--color-border)] px-3 py-3">
        <div className="mb-2 text-sm font-semibold text-[var(--color-text-1)]">
          {t("wiki.directoryTitle")}
        </div>
        <Input.Search
          allowClear
          size="small"
          value={search}
          placeholder={t("wiki.filterNamePlaceholder")}
          onChange={(event) => onSearchChange(event.target.value)}
          onSearch={onSearchChange}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        <Tree
          blockNode
          showIcon={false}
          expandedKeys={effectiveExpandedKeys}
          selectedKeys={selectedKeys}
          treeData={treeData}
          className={[
            "wiki-knowledge-tree bg-transparent",
            // 节点行：无图标、圆角、紧凑内边距（对齐 canvas PageRow）
            "[&_.ant-tree-treenode]:w-full [&_.ant-tree-treenode]:py-[1px]",
            "[&_.ant-tree-node-content-wrapper]:min-w-0",
            "[&_.ant-tree-node-content-wrapper]:rounded-md",
            "[&_.ant-tree-node-content-wrapper]:border-transparent",
            "[&_.ant-tree-node-content-wrapper]:px-2.5 [&_.ant-tree-node-content-wrapper]:py-1.5",
            "[&_.ant-tree-node-content-wrapper:hover]:!bg-[var(--color-fill-2)]",
            "[&_.ant-tree-title]:block [&_.ant-tree-title]:min-w-0",
            // 选中：浅填充 + 主题色文字（对齐 canvas fill.secondary / accent.primary）
            // Ant 版本差异：selected 可能在 content-wrapper 或 treenode 上
            "[&_.ant-tree-node-content-wrapper.ant-tree-node-selected]:!bg-[var(--color-fill-2)]",
            "[&_.ant-tree-node-content-wrapper.ant-tree-node-selected]:!text-[var(--color-primary)]",
            "[&_.ant-tree-node-content-wrapper.ant-tree-node-selected]:font-medium",
            "[&_.ant-tree-node-selected_.ant-tree-node-content-wrapper]:!bg-[var(--color-fill-2)]",
            "[&_.ant-tree-node-selected_.ant-tree-node-content-wrapper]:!text-[var(--color-primary)]",
            "[&_.ant-tree-node-selected_.ant-tree-node-content-wrapper]:font-medium",
            // 展开箭头保持中性色，不抢视觉
            "[&_.ant-tree-switcher]:text-[var(--color-text-3)]",
            "[&_.ant-tree-switcher]:flex [&_.ant-tree-switcher]:items-center [&_.ant-tree-switcher]:justify-center",
          ].join(" ")}
          onExpand={(keys) => setExpandedKeys(keys)}
          onSelect={(keys) => {
            if (!keys.length) return;
            const key = String(keys[0]);
            if (!key.startsWith("page:")) return;
            const id = Number(key.replace("page:", ""));
            if (Number.isInteger(id) && id > 0) onSelectPage(id);
          }}
        />
      </div>
      <div className="border-t border-[var(--color-border)] px-3 py-2 text-[11px] text-[var(--color-text-3)]">
        {t("wiki.directoryPageCount", undefined, { count: pages.length })}
      </div>
    </aside>
  );
};

export const toWikiTreePages = (
  pages: KnowledgePage[],
): WikiTreePageItem[] =>
  pages.map((page) => ({
    id: page.id,
    title: page.title,
    page_type: page.page_type,
    directory: page.directory ?? null,
  }));

export default WikiDirectoryTree;
