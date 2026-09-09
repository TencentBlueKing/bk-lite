import { describe, expect, it } from "vitest";
import type {
  WikiDirectoryNode,
  WikiFrozenStructureSnapshot,
} from "@/app/opspilot/types/wiki";
import {
  canDeleteKnowledgeDirectory,
  collectDirectorySubtreeIds,
  isTopLevelDirectory,
  omitDirectoriesFromSnapshot,
  pageIdsInDirectories,
} from "../wikiDirectoryTreeOps";

const directory = (
  partial: Partial<WikiDirectoryNode> & Pick<WikiDirectoryNode, "id" | "name">,
): WikiDirectoryNode => ({
  key: `dir-${partial.id}`,
  parent_id: null,
  order: 0,
  status: "active",
  is_system: false,
  accepts_pages: true,
  direct_page_count: 0,
  total_page_count: 0,
  children: [],
  ...partial,
});

describe("wikiDirectoryTreeOps", () => {
  const unclassified = directory({
    id: 1,
    name: "未分类",
    is_system: true,
    children: [
      directory({ id: 11, name: "metrics", parent_id: 1 }),
      directory({
        id: 12,
        name: "tables",
        parent_id: 1,
        children: [directory({ id: 121, name: "nested", parent_id: 12 })],
      }),
    ],
  });
  const concept = directory({ id: 2, name: "概念" });
  const roots = [unclassified, concept];

  it("collects a nested directory and its descendants", () => {
    expect(collectDirectorySubtreeIds(roots, 12)).toEqual([12, 121]);
  });

  it("only allows deleting non-top-level non-system directories", () => {
    expect(isTopLevelDirectory(roots, 2)).toBe(true);
    expect(canDeleteKnowledgeDirectory(roots, concept, 1)).toBe(false);
    expect(canDeleteKnowledgeDirectory(roots, unclassified, 1)).toBe(false);
    expect(
      canDeleteKnowledgeDirectory(roots, unclassified.children[0], 1),
    ).toBe(true);
  });

  it("maps pages in the omitted subtree", () => {
    expect(
      pageIdsInDirectories(
        [
          { id: 8, directory: 12 },
          { id: 9, directory: 2 },
          { id: 10, directory: 121 },
        ],
        [12, 121],
      ),
    ).toEqual([8, 10]);
  });

  it("omits directories from a structure snapshot while keeping keys", () => {
    const snapshot: WikiFrozenStructureSnapshot = {
      format_version: 1,
      page_types: ["concept"],
      directories: [
        {
          id: 1,
          key: "__unclassified__",
          origin: "system",
          status: "active",
          name: "未分类",
          description: "",
          order: 0,
          rules: { allowed_page_types: ["concept"], default_for_page_types: [] },
          parent: null,
        },
        {
          id: 12,
          key: "tables",
          origin: "manual",
          status: "active",
          name: "tables",
          description: "",
          order: 10,
          rules: { allowed_page_types: ["concept"], default_for_page_types: [] },
          parent: { id: 1, key: "__unclassified__" },
        },
      ],
    };
    const remaining = omitDirectoriesFromSnapshot(snapshot, [12]);
    expect(remaining.map((item) => item.id)).toEqual([1]);
    expect(remaining[0].kind).toBe("existing");
  });
});
