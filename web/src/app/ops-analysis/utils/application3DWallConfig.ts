import { APPLICATION3D_DENSE_TIER_MAX } from '@/app/ops-analysis/components/widgets/application3D/application3DLayout';

export const APPLICATION3D_WALL_PAGE_SIZE_MIN = 1;
export const APPLICATION3D_WALL_PAGE_SIZE_MAX = APPLICATION3D_DENSE_TIER_MAX;
export const APPLICATION3D_WALL_PAGE_SIZE_DEFAULT = 24;
export const APPLICATION3D_WALL_DWELL_MIN = 5;
export const APPLICATION3D_WALL_DWELL_MAX = 60;
export const APPLICATION3D_WALL_DWELL_DEFAULT = 10;

export const APPLICATION3D_PAGE_EFFECTS = ['cut', 'slide', 'fade', 'flip'] as const;

export type Application3DPageEffect = (typeof APPLICATION3D_PAGE_EFFECTS)[number];

export interface Application3DWallConfig {
  pageSize: number;
  alarmPagesEnabled: boolean;
  alarmPageSize: number;
  autoPageEnabled: boolean;
  dwellSeconds: number;
  pageEffect: Application3DPageEffect;
}

const clampInt = (value: unknown, min: number, max: number, fallback: number) => {
  const parsed = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(parsed)));
};

const isPageEffect = (value: unknown): value is Application3DPageEffect =>
  typeof value === 'string' && (APPLICATION3D_PAGE_EFFECTS as readonly string[]).includes(value);

/** Missing or invalid fields keep the wall on today's manual 24-card pages. */
export const resolveApplication3DWallConfig = (
  raw?: Partial<Application3DWallConfig> | null,
): Application3DWallConfig => ({
  pageSize: clampInt(
    raw?.pageSize,
    APPLICATION3D_WALL_PAGE_SIZE_MIN,
    APPLICATION3D_WALL_PAGE_SIZE_MAX,
    APPLICATION3D_WALL_PAGE_SIZE_DEFAULT,
  ),
  alarmPagesEnabled: raw?.alarmPagesEnabled === true,
  alarmPageSize: clampInt(
    raw?.alarmPageSize,
    APPLICATION3D_WALL_PAGE_SIZE_MIN,
    APPLICATION3D_WALL_PAGE_SIZE_MAX,
    APPLICATION3D_WALL_PAGE_SIZE_DEFAULT,
  ),
  autoPageEnabled: raw?.autoPageEnabled === true,
  dwellSeconds: clampInt(
    raw?.dwellSeconds,
    APPLICATION3D_WALL_DWELL_MIN,
    APPLICATION3D_WALL_DWELL_MAX,
    APPLICATION3D_WALL_DWELL_DEFAULT,
  ),
  pageEffect: isPageEffect(raw?.pageEffect) ? raw.pageEffect : 'slide',
});
