"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

const DEFAULT_PAGE = 1;
const DEFAULT_PAGE_SIZE = 20;
const DEFAULT_STATUS = "active";
const DEFAULT_VIEW = "page";

type HistoryMode = "push" | "replace";
export type WikiView = "page" | "graph";
type WikiQueryKey =
  | "directory"
  | "include_descendants"
  | "page"
  | "page_size"
  | "search"
  | "page_type"
  | "status"
  | "wiki_view"
  | "wiki_page";
type WikiQueryPatch = Partial<
  Record<WikiQueryKey, string | number | boolean | null>
>;

const positiveInteger = (value: string | null, fallback: number) => {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
};

const isTrue = (value: string | null) => value === "1" || value === "true";

export interface WikiDirectoryQuery {
  view: WikiView;
  directoryId: number | null;
  includeDescendants: boolean;
  page: number;
  pageSize: number;
  search: string;
  pageType: string;
  status: string;
  selectedPageId: number | null;
  setView: (view: WikiView, history?: HistoryMode) => void;
  setDirectoryId: (directoryId: number | null, history?: HistoryMode) => void;
  setIncludeDescendants: (includeDescendants: boolean) => void;
  setSearch: (search: string, history?: HistoryMode) => void;
  setPageType: (pageType: string) => void;
  setStatus: (status: string) => void;
  setPagination: (page: number, pageSize: number) => void;
  setSelectedPageId: (
    pageId: number | null,
    history?: HistoryMode,
  ) => void;
}

export const useWikiDirectoryQuery = (): WikiDirectoryQuery => {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentQuery = searchParams?.toString() || "";
  const latestQueryRef = useRef(currentQuery);
  const pendingQueriesRef = useRef<string[]>([]);

  useEffect(() => {
    const pendingIndex = pendingQueriesRef.current.indexOf(currentQuery);
    if (pendingIndex >= 0) {
      pendingQueriesRef.current = pendingQueriesRef.current.slice(
        pendingIndex + 1,
      );
      latestQueryRef.current =
        pendingQueriesRef.current[pendingQueriesRef.current.length - 1] ??
        currentQuery;
      return;
    }
    pendingQueriesRef.current = [];
    latestQueryRef.current = currentQuery;
  }, [currentQuery, pathname]);

  const query = useMemo(() => {
    const directory = positiveInteger(
      searchParams?.get("directory") ?? null,
      0,
    );
    const wikiPage = positiveInteger(
      searchParams?.get("wiki_page") ?? null,
      0,
    );
    return {
      view:
        searchParams?.get("wiki_view") === "graph"
          ? ("graph" as const)
          : (DEFAULT_VIEW as WikiView),
      directoryId: directory || null,
      includeDescendants: isTrue(
        searchParams?.get("include_descendants") ?? null,
      ),
      page: positiveInteger(searchParams?.get("page") ?? null, DEFAULT_PAGE),
      pageSize: positiveInteger(
        searchParams?.get("page_size") ?? null,
        DEFAULT_PAGE_SIZE,
      ),
      search: searchParams?.get("search") ?? "",
      pageType: searchParams?.get("page_type") ?? "",
      status: searchParams?.get("status") || DEFAULT_STATUS,
      selectedPageId: wikiPage || null,
    };
  }, [searchParams]);

  const updateQuery = useCallback(
    (patch: WikiQueryPatch, history: HistoryMode = "push") => {
      const params = new URLSearchParams(latestQueryRef.current);

      Object.entries(patch).forEach(([rawKey, value]) => {
        const key = rawKey as WikiQueryKey;
        const text =
          typeof value === "string" ? value.trim() : String(value ?? "");
        const isDefault =
          value === null ||
          text === "" ||
          (key === "include_descendants" && value !== true) ||
          (key === "page" && value === DEFAULT_PAGE) ||
          (key === "page_size" && value === DEFAULT_PAGE_SIZE) ||
          (key === "status" && text === DEFAULT_STATUS) ||
          (key === "wiki_view" && text === DEFAULT_VIEW) ||
          (key === "wiki_page" && !(Number(text) > 0));

        if (isDefault) {
          params.delete(key);
        } else {
          params.set(key, key === "include_descendants" ? "true" : text);
        }
      });

      const nextQuery = params.toString();
      if (nextQuery === latestQueryRef.current) return;
      latestQueryRef.current = nextQuery;
      pendingQueriesRef.current.push(nextQuery);
      const href = nextQuery ? `${pathname}?${nextQuery}` : pathname;
      if (history === "replace") router.replace(href, { scroll: false });
      else router.push(href, { scroll: false });
    },
    [pathname, router],
  );

  return useMemo(
    () => ({
      ...query,
      setView: (view: WikiView, history: HistoryMode = "push") =>
        updateQuery({ wiki_view: view }, history),
      setDirectoryId: (
        directoryId: number | null,
        history: HistoryMode = "push",
      ) =>
        updateQuery(
          {
            directory: directoryId && directoryId > 0 ? directoryId : null,
            page: DEFAULT_PAGE,
          },
          history,
        ),
      setIncludeDescendants: (includeDescendants: boolean) =>
        updateQuery({
          include_descendants: includeDescendants,
          page: DEFAULT_PAGE,
        }),
      setSearch: (search: string, history: HistoryMode = "replace") =>
        updateQuery({ search, page: DEFAULT_PAGE }, history),
      setPageType: (pageType: string) =>
        updateQuery({ page_type: pageType, page: DEFAULT_PAGE }),
      setStatus: (status: string) =>
        updateQuery({ status, page: DEFAULT_PAGE }),
      setPagination: (page: number, pageSize: number) =>
        updateQuery({
          page: Math.max(Math.trunc(page), DEFAULT_PAGE),
          page_size: Math.max(Math.trunc(pageSize), 1),
        }),
      setSelectedPageId: (
        pageId: number | null,
        history: HistoryMode = "push",
      ) =>
        updateQuery(
          {
            wiki_page: pageId && pageId > 0 ? pageId : null,
          },
          history,
        ),
    }),
    [query, updateQuery],
  );
};

export default useWikiDirectoryQuery;
