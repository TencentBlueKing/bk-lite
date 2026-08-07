"use client";

import { useMemo } from "react";
import { TreeSelect } from "antd";
import type { WikiDirectoryNode } from "@/app/opspilot/types/wiki";

interface DirectoryTreeSelectNode {
  title: string;
  value: number;
  key: number;
  disabled: boolean;
  searchText: string;
  children: DirectoryTreeSelectNode[];
}

export interface WikiDirectorySelectProps {
  directories: WikiDirectoryNode[];
  value?: number;
  disabled?: boolean;
  allowClear?: boolean;
  placeholder?: string;
  className?: string;
  excludedDirectoryIds?: number[];
  acceptsPagesOnly?: boolean;
  onChange: (directoryId: number | undefined) => void;
}

const toTreeSelectData = (
  directories: WikiDirectoryNode[],
  excludedDirectoryIds: Set<number>,
  acceptsPagesOnly: boolean,
  ancestors: string[] = [],
): DirectoryTreeSelectNode[] =>
  directories.map((directory) => {
    const path = [...ancestors, directory.name];
    return {
      title: directory.name,
      value: directory.id,
      key: directory.id,
      disabled:
        excludedDirectoryIds.has(directory.id) ||
        directory.status !== "active" ||
        (acceptsPagesOnly && !directory.accepts_pages),
      searchText: path.join(" / "),
      children: toTreeSelectData(
        directory.children || [],
        excludedDirectoryIds,
        acceptsPagesOnly,
        path,
      ),
    };
  });

const WikiDirectorySelect = ({
  directories,
  value,
  disabled = false,
  allowClear = false,
  placeholder,
  className = "w-full",
  excludedDirectoryIds = [],
  acceptsPagesOnly = true,
  onChange,
}: WikiDirectorySelectProps) => {
  const excludedIds = useMemo(
    () => new Set(excludedDirectoryIds),
    [excludedDirectoryIds],
  );
  const treeData = useMemo(
    () => toTreeSelectData(directories, excludedIds, acceptsPagesOnly),
    [acceptsPagesOnly, directories, excludedIds],
  );

  return (
    <TreeSelect<number>
      value={value}
      disabled={disabled}
      allowClear={allowClear}
      treeData={treeData}
      className={className}
      placeholder={placeholder}
      treeDefaultExpandAll
      showSearch
      treeNodeFilterProp="searchText"
      onChange={onChange}
    />
  );
};

export default WikiDirectorySelect;
