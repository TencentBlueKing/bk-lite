export interface InsertTile {
  x: number;
  y: number;
}

export interface InsertRegion {
  from: InsertTile;
  to: InsertTile;
}

const NAME_LIMIT = 100;
/** Open-canvas rows stay short enough to scan, then continue one row further back. */
const OPEN_ROW_WIDTH = 6;
const MAX_ROWS = 200;

export const DEFAULT_ARCHITECTURE_ICON_ID = 'cmdb-cc-default';

const iconKeyFromReference = (reference: string): string => {
  const file = reference.trim().split('/').pop() ?? '';
  return file.replace(/\.svg$/i, '').split('_')[0] ?? '';
};

const paletteIdForKey = (key: string): string => (key ? `cmdb-${key}` : '');

export function architectureIconIdFromUrl(url: string): string {
  let path = url;
  try {
    path = decodeURIComponent(url);
  } catch {
    path = url;
  }
  const match = path.match(/\/(?:icons-realistic|icons)\/([^/?#]+)\.svg$/);
  if (!match) return DEFAULT_ARCHITECTURE_ICON_ID;
  return paletteIdForKey(match[1].split('_')[0]) || DEFAULT_ARCHITECTURE_ICON_ID;
}

/**
 * The model icon may be stored as a flat `icons/...` reference. Use that key
 * when the 2.5D palette has the same icon; otherwise use the resolved URL.
 */
export function architectureIconIdForModel(
  icn: string | undefined,
  resolvedUrl: string,
  available: readonly string[],
): string {
  const fromModel = paletteIdForKey(iconKeyFromReference(icn ?? ''));
  if (fromModel && available.includes(fromModel)) return fromModel;
  return pickArchitectureIcon(architectureIconIdFromUrl(resolvedUrl), available);
}

export function pickArchitectureIcon(preferred: string, available: readonly string[]): string {
  if (available.includes(preferred)) return preferred;
  if (available.includes(DEFAULT_ARCHITECTURE_ICON_ID)) return DEFAULT_ARCHITECTURE_ICON_ID;
  return preferred;
}

export function assetInsertLabel(
  hit: { inst_name?: string; ip_addr?: string },
  unnamed: string,
): string {
  const name = hit.inst_name?.trim() ?? '';
  if (name) return name.slice(0, NAME_LIMIT);
  const ip = hit.ip_addr?.trim() ?? '';
  if (ip) return ip.slice(0, NAME_LIMIT);
  return unnamed.slice(0, NAME_LIMIT);
}

export function insertSelection<T extends { inst_uuid: string }>(
  picked: readonly T[],
  placed: ReadonlySet<string>,
): T[] {
  const seen = new Set<string>();
  const result: T[] = [];
  for (const hit of picked) {
    const uuid = hit.inst_uuid.trim();
    if (!uuid || placed.has(uuid) || seen.has(uuid)) continue;
    seen.add(uuid);
    result.push(hit);
  }
  return result;
}

const tileKey = (tile: InsertTile) => `${tile.x},${tile.y}`;

const boundsOf = (region: InsertRegion) => {
  const minX = Math.min(region.from.x, region.to.x);
  const maxX = Math.max(region.from.x, region.to.x);
  const minY = Math.min(region.from.y, region.to.y);
  const maxY = Math.max(region.from.y, region.to.y);
  return { minX, maxX, minY, maxY };
};

const insideTiles = (region: InsertRegion, taken: Set<string>): InsertTile[] => {
  const { minX, maxX, minY, maxY } = boundsOf(region);
  const tiles: InsertTile[] = [];
  for (let x = minX; x <= maxX; x += 1) {
    for (let y = minY; y <= maxY; y += 1) {
      const tile = { x, y };
      if (!taken.has(tileKey(tile))) tiles.push(tile);
    }
  }
  tiles.sort((a, b) => (a.x + a.y) - (b.x + b.y) || a.x - b.x);
  return tiles;
};

const takeRow = (
  taken: Set<string>,
  sum: number,
  startX: number,
  width: number,
  want: number,
): InsertTile[] => {
  const row: InsertTile[] = [];
  for (let step = 0; step < width && row.length < want; step += 1) {
    const tile = { x: startX + step, y: sum - (startX + step) };
    if (taken.has(tileKey(tile))) continue;
    row.push(tile);
  }
  return row;
};

/**
 * Empty tiles, front to back and left to right.
 * A selected area is filled first. Tiles that do not fit sit on rows in front of it.
 * With no area, packing starts at the viewport center and continues backward.
 */
export function planInsertTiles(input: {
  count: number;
  occupied: readonly InsertTile[];
  region: InsertRegion | null;
  origin: InsertTile;
}): InsertTile[] {
  if (input.count <= 0) return [];
  const taken = new Set(input.occupied.map(tileKey));
  const placed: InsertTile[] = [];
  const claim = (tile: InsertTile) => {
    taken.add(tileKey(tile));
    placed.push(tile);
  };

  if (input.region) {
    for (const tile of insideTiles(input.region, taken)) {
      if (placed.length >= input.count) return placed;
      claim(tile);
    }
    const { minX, minY, maxX } = boundsOf(input.region);
    const minSum = minX + minY;
    const width = maxX - minX + 1;
    for (let row = 1; row <= MAX_ROWS && placed.length < input.count; row += 1) {
      for (const tile of takeRow(taken, minSum - row, minX, width, input.count - placed.length)) {
        claim(tile);
      }
    }
    return placed;
  }

  const originSum = input.origin.x + input.origin.y;
  for (let depth = 0; depth <= MAX_ROWS && placed.length < input.count; depth += 1) {
    for (const tile of takeRow(
      taken,
      originSum + depth,
      input.origin.x,
      OPEN_ROW_WIDTH,
      input.count - placed.length,
    )) {
      claim(tile);
    }
  }
  return placed;
}
