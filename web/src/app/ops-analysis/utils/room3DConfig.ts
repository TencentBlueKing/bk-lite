import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import type {
  Room3DConfig,
  Room3DRackTopField,
  Room3DRackTopLines,
  Room3DRoomOption,
} from '@/app/ops-analysis/types/sceneWidget';
import { isValidCmdbInstanceUuid } from '@/app/ops-analysis/utils/cmdbInstanceUuid';

export type Room3DSelection =
  | { status: 'empty'; rooms: Room3DRoomOption[] }
  | { status: 'unavailable'; rooms: Room3DRoomOption[] }
  | { status: 'ready'; roomId: string; rooms: Room3DRoomOption[] };

export const DEFAULT_ROOM3D_RACK_TOP_LINE1: Room3DRackTopField = 'location';
export const DEFAULT_ROOM3D_RACK_TOP_LINE2: Room3DRackTopField = 'type';

export const ROOM3D_RACK_TOP_FIELDS: readonly Room3DRackTopField[] = [
  'location',
  'name',
  'type',
  'state',
];

const normalizeRoomId = (value: unknown): string =>
  isValidCmdbInstanceUuid(value) ? value : '';

const isRackTopField = (value: unknown): value is Room3DRackTopField =>
  value === 'location' ||
  value === 'name' ||
  value === 'type' ||
  value === 'state';

export const readRoom3DRackTopLines = (
  config?: Room3DConfig | null,
): Room3DRackTopLines => {
  const raw1 = config?.rackTopLine1;
  const raw2 = config?.rackTopLine2;
  if (raw1 === undefined && raw2 === undefined) {
    return {
      line1: DEFAULT_ROOM3D_RACK_TOP_LINE1,
      line2: DEFAULT_ROOM3D_RACK_TOP_LINE2,
    };
  }
  return {
    line1: isRackTopField(raw1) ? raw1 : DEFAULT_ROOM3D_RACK_TOP_LINE1,
    line2: isRackTopField(raw2) ? raw2 : '',
  };
};

const persistRackTopLines = (
  config?: Room3DConfig | null,
): Pick<Room3DConfig, 'rackTopLine1' | 'rackTopLine2'> => {
  if (config?.rackTopLine1 === undefined && config?.rackTopLine2 === undefined) {
    return {};
  }
  const { line1, line2 } = readRoom3DRackTopLines(config);
  if (
    line1 === DEFAULT_ROOM3D_RACK_TOP_LINE1 &&
    line2 === DEFAULT_ROOM3D_RACK_TOP_LINE2
  ) {
    return {};
  }
  return {
    rackTopLine1: line1,
    rackTopLine2: line2,
  };
};

export const persistRoom3DConfig = (
  config?: Room3DConfig | null,
): Room3DConfig => {
  const serverRoomId = normalizeRoomId(config?.serverRoomId?.trim());
  return {
    ...(serverRoomId ? { serverRoomId } : {}),
    ...persistRackTopLines(config),
  };
};

export const hydrateRoom3DConfig = (
  config?: Room3DConfig | null,
): Room3DConfig => {
  const persisted = persistRoom3DConfig(config);
  const lines = readRoom3DRackTopLines(config);
  return {
    ...(persisted.serverRoomId ? { serverRoomId: persisted.serverRoomId } : {}),
    rackTopLine1: lines.line1,
    ...(lines.line2 ? { rackTopLine2: lines.line2 } : {}),
  };
};

export const readPersistedServerRoomId = (
  valueConfig?: ValueConfig | null,
): string => {
  const fromScene = persistRoom3DConfig(valueConfig?.room3D).serverRoomId;
  if (fromScene) return fromScene;
  const params = valueConfig?.dataSourceParams;
  if (!Array.isArray(params)) return '';
  const param = params.find((item) => item?.name === 'server_room_id');
  return normalizeRoomId(param?.value);
};

export const resolveRoom3DSelection = ({
  rooms,
  savedRoomId,
  runtimeRoomId,
}: {
  rooms: Room3DRoomOption[];
  savedRoomId?: string;
  runtimeRoomId?: string;
}): Room3DSelection => {
  const visible = rooms.filter((item) => normalizeRoomId(item.id));
  if (!visible.length) {
    return { status: 'empty', rooms: [] };
  }

  const visibleIds = new Set(visible.map((item) => item.id));
  const runtimeId = normalizeRoomId(runtimeRoomId);
  if (runtimeId && visibleIds.has(runtimeId)) {
    return { status: 'ready', roomId: runtimeId, rooms: visible };
  }

  const savedId = normalizeRoomId(savedRoomId);
  if (savedId && visibleIds.has(savedId)) {
    return { status: 'ready', roomId: savedId, rooms: visible };
  }
  if (savedId) {
    return { status: 'unavailable', rooms: visible };
  }

  return { status: 'ready', roomId: visible[0].id, rooms: visible };
};
