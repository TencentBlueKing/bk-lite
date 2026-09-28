import { SearchFilters } from '@/components/search-combination/types';

export function buildNodeExportRequest({
  selectedIds,
  cloudRegionId,
  filters,
  unassignedOnly
}: {
  selectedIds: Array<string | number>;
  cloudRegionId: number | string;
  filters?: SearchFilters;
  unassignedOnly: boolean;
}): { query: { unassigned?: boolean }; body: Record<string, unknown> } {
  const query = unassignedOnly ? { unassigned: true } : {};
  const ids = selectedIds.map(String).filter(Boolean);
  if (ids.length) {
    return {
      query,
      body: {
        cloud_region_id: cloudRegionId,
        selected_ids: ids
      }
    };
  }
  const body: Record<string, unknown> = { cloud_region_id: cloudRegionId };
  if (filters && Object.keys(filters).length > 0) {
    body.filters = filters;
  }
  return { query, body };
}

export function nodeExportQueryString(query: { unassigned?: boolean }): string {
  if (!query.unassigned) return '';
  return '?unassigned=true';
}

export function parseContentDispositionFilename(
  header: string | null | undefined
): string {
  if (!header) return '';
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star) {
    const raw = star[1].trim().replace(/^["']|["']$/g, '');
    try {
      return decodeURIComponent(raw);
    } catch {
      return raw;
    }
  }
  const plain = /(?:^|;)\s*filename=(?!\*)("(?:\\.|[^"\\])*"|[^;]+)/i.exec(
    header
  );
  if (!plain) return '';
  const value = plain[1].trim();
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }
  return value;
}
