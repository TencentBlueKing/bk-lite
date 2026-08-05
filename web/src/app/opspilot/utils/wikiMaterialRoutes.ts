/** 知识库资料详情：同页 ?tab=material&materialId= */

const WIKI_SHARED_QUERY_KEYS = ["id", "name", "desc"] as const;

/** 各左侧页签私有查询参数；切走页签时不应残留。 */
const WIKI_TAB_OWNED_QUERY_KEYS: Record<string, readonly string[]> = {
  material: ["materialId"],
  knowledge: [
    "wiki_page",
    "wiki_view",
    "directory",
    "include_descendants",
    "page",
    "page_size",
    "search",
    "page_type",
    "status",
  ],
};

function toSearchParams(
  searchParams?: URLSearchParams | string | null,
): URLSearchParams {
  return new URLSearchParams(
    typeof searchParams === "string"
      ? searchParams
      : searchParams?.toString() || "",
  );
}

export function buildWikiDetailTabPath(options: {
  kbId: number;
  tab: string;
  searchParams?: URLSearchParams | string | null;
}): string {
  const incoming = toSearchParams(options.searchParams);
  const params = new URLSearchParams();

  for (const key of WIKI_SHARED_QUERY_KEYS) {
    const value = incoming.get(key);
    if (value) params.set(key, value);
  }

  if (Number.isFinite(options.kbId) && options.kbId > 0) {
    params.set("id", String(options.kbId));
  }
  params.set("tab", options.tab);

  // 保留目标页签自己的状态；资料菜单始终进列表，不带 materialId。
  const ownedKeys = WIKI_TAB_OWNED_QUERY_KEYS[options.tab] || [];
  for (const key of ownedKeys) {
    if (key === "materialId") continue;
    const value = incoming.get(key);
    if (value) params.set(key, value);
  }

  return `/opspilot/wiki/detail?${params.toString()}`;
}

export function buildWikiMaterialDetailPath(options: {
  kbId: number;
  materialId: number;
  searchParams?: URLSearchParams | string | null;
}): string {
  const params = toSearchParams(options.searchParams);
  params.set("id", String(options.kbId));
  params.set("tab", "material");
  params.set("materialId", String(options.materialId));
  return `/opspilot/wiki/detail?${params.toString()}`;
}

export function buildWikiMaterialListPath(options: {
  kbId: number;
  searchParams?: URLSearchParams | string | null;
}): string {
  const params = toSearchParams(options.searchParams);
  params.set("id", String(options.kbId));
  params.set("tab", "material");
  params.delete("materialId");
  return `/opspilot/wiki/detail?${params.toString()}`;
}

export function openWikiMaterialDetailInNewWindow(options: {
  kbId: number;
  materialId: number;
}): void {
  const href = buildWikiMaterialDetailPath(options);
  window.open(href, "_blank", "noopener,noreferrer");
}
