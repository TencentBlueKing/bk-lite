export interface Room3DResponse {
  room: {
    id: string;
    name: string;
  };
  racks: Room3DRack[];
  notice?: string;
}

export interface Room3DRack {
  rack_id: string;
  rack_name: string;
  row: number;
  col: number;
  location?: string;
  rack_type?: string | null;
  rack_type_name?: string | null;
  u_count?: number;
  used_u?: number;
  free_u?: number;
  device_count?: number;
  unplaced_device_count?: number;
  devices?: Room3DDevice[];
  is_conflict?: boolean;
  conflict_racks?: Room3DRack[];
}

export interface Room3DDevice {
  device_id: string;
  device_name: string;
  model_id?: string | null;
  rack_u_start?: number | null;
  u_size?: number | null;
  status?: string | null;
}

export type Room3DRenderableDevice = Room3DDevice;

export type Room3DValidationResult =
  | { ok: true; data: Room3DResponse }
  | { ok: false; error: string };

export type Room3DTranslator = (id: string) => string;

export interface Room3DDisplayOptions {
  immersive: boolean;
  transparentScene: boolean;
}

export const getRoom3DDisplayOptions = (config?: {
  appearance?: { frame?: string };
}): Room3DDisplayOptions => {
  const immersive = config?.appearance?.frame === 'bare';
  return {
    immersive,
    transparentScene: immersive,
  };
};

const OPTIONAL_NUMBER_FIELDS: Array<keyof Room3DRack> = [
  'u_count',
  'used_u',
  'free_u',
  'device_count',
  'unplaced_device_count',
];

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0;

const isPositiveInteger = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 1;

const exposeI18nKey: Room3DTranslator = (id) => id;

const validateOptionalNumberFields = (
  rack: Record<string, unknown>,
  index: number,
  t: Room3DTranslator,
) => {
  for (const field of OPTIONAL_NUMBER_FIELDS) {
    const value = rack[field];
    if (value === undefined || value === null) {
      continue;
    }
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      return `${t('dashboard.room3DRackIndexPrefix')}${index + 1}${t('dashboard.room3DRackNumberFieldError')}${String(field)}`;
    }
  }

  return '';
};

const normalizeRoom3DDevices = (
  value: unknown,
  rackIndex: number,
  t: Room3DTranslator,
): { devices?: Room3DDevice[]; error?: string } => {
  if (value === undefined || value === null) {
    return {};
  }
  if (!Array.isArray(value)) {
    return {
      error: `${t('dashboard.room3DRackIndexPrefix')}${rackIndex + 1}${t('dashboard.room3DDevicesArrayError')}`,
    };
  }

  const devices: Room3DDevice[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const device = value[index];
    if (!isRecord(device)) {
      return {
        error: `${t('dashboard.room3DRackIndexPrefix')}${rackIndex + 1}${t('dashboard.room3DDeviceIndexPrefix')}${index + 1}${t('dashboard.room3DDeviceFormatError')}`,
      };
    }
    if (
      !isNonEmptyString(device.device_id) ||
      !isNonEmptyString(device.device_name) ||
      !isPositiveInteger(device.rack_u_start) ||
      !isPositiveInteger(device.u_size)
    ) {
      return {
        error: `${t('dashboard.room3DRackIndexPrefix')}${rackIndex + 1}${t('dashboard.room3DDeviceIndexPrefix')}${index + 1}${t('dashboard.room3DDeviceRequiredError')}`,
      };
    }

    devices.push({
      device_id: String(device.device_id ?? '').trim(),
      device_name: String(device.device_name ?? '').trim(),
      model_id:
        typeof device.model_id === 'string'
          ? device.model_id
          : device.model_id === null
            ? null
            : undefined,
      rack_u_start: device.rack_u_start,
      u_size: device.u_size,
      status:
        typeof device.status === 'string'
          ? device.status
          : device.status === null
            ? null
            : undefined,
    });
  }

  return { devices };
};

export const getRoom3DColumnLabel = (col: number) => {
  if (!Number.isInteger(col) || col < 1) {
    return '';
  }

  let value = col;
  let label = '';
  while (value > 0) {
    const remainder = (value - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    value = Math.floor((value - 1) / 26);
  }

  return label;
};

export const getRoom3DRowLabel = (row: number) => getRoom3DColumnLabel(row);

export const getRoom3DStandardLocation = (row: number, col: number) => {
  const rowLabel = getRoom3DRowLabel(row);
  if (!rowLabel || !Number.isInteger(col) || col < 1) {
    return '';
  }
  return `${rowLabel}${String(col).padStart(2, '0')}`;
};

export const getRoom3DPositionLabel = (rack: Pick<Room3DRack, 'row' | 'col' | 'location'>) =>
  typeof rack.location === 'string' && rack.location.trim()
    ? rack.location.trim()
    : getRoom3DStandardLocation(rack.row, rack.col);

export const getRoom3DRackDevices = (rack: Room3DRack): Room3DRenderableDevice[] => {
  return rack.devices ?? [];
};

const getRoom3DCellKey = (rack: Pick<Room3DRack, 'row' | 'col'>) => `${rack.row}:${rack.col}`;

export const getRoom3DSceneRacks = (roomData: Pick<Room3DResponse, 'racks'>): Room3DRack[] => {
  const groups = new Map<string, Room3DRack[]>();
  roomData.racks.forEach((rack) => {
    const key = getRoom3DCellKey(rack);
    groups.set(key, [...(groups.get(key) || []), rack]);
  });

  const sceneRacks: Room3DRack[] = [];
  groups.forEach((group) => {
    if (group.length === 1) {
      sceneRacks.push(group[0]);
      return;
    }
    const firstRack = group[0];
    sceneRacks.push({
      ...firstRack,
      rack_id: `conflict:${firstRack.row}:${firstRack.col}`,
      rack_name: getRoom3DPositionLabel(firstRack),
      location: getRoom3DPositionLabel(firstRack),
      devices: [],
      is_conflict: true,
      conflict_racks: group,
    });
  });

  return sceneRacks;
};

export const validateRoom3DData = (
  value: unknown,
  t: Room3DTranslator = exposeI18nKey,
): Room3DValidationResult => {
  if (!isRecord(value) || !isRecord(value.room) || !Array.isArray(value.racks)) {
    return { ok: false, error: t('dashboard.room3DFormatError') };
  }

  const { room, racks } = value;
  if (!isNonEmptyString(room.id) || !isNonEmptyString(room.name)) {
    return { ok: false, error: t('dashboard.room3DRoomRequiredError') };
  }

  const normalizedRacks: Room3DRack[] = [];

  for (let index = 0; index < racks.length; index += 1) {
    const rack = racks[index];
    if (!isRecord(rack)) {
      return {
        ok: false,
        error: `${t('dashboard.room3DRackIndexPrefix')}${index + 1}${t('dashboard.room3DRackFormatError')}`,
      };
    }

    if (
      !isNonEmptyString(rack.rack_id) ||
      !isNonEmptyString(rack.rack_name) ||
      !isPositiveInteger(rack.row) ||
      !isPositiveInteger(rack.col)
    ) {
      return {
        ok: false,
        error: `${t('dashboard.room3DRackIndexPrefix')}${index + 1}${t('dashboard.room3DRackRequiredError')}`,
      };
    }

    const rackId = rack.rack_id;
    const rackName = rack.rack_name;
    const row = rack.row;
    const col = rack.col;
    const location = isNonEmptyString(rack.location)
      ? rack.location.trim()
      : getRoom3DStandardLocation(row, col);
    const rawRackType = rack.rack_type;
    const rackType: Room3DRack['rack_type'] =
      typeof rawRackType === 'string'
        ? rawRackType
        : rawRackType === null
          ? null
          : undefined;
    const rawRackTypeName = rack.rack_type_name;
    const rackTypeName: Room3DRack['rack_type_name'] =
      isNonEmptyString(rawRackTypeName)
        ? rawRackTypeName.trim()
        : rawRackTypeName === null
          ? null
          : undefined;
    const numberFieldError = validateOptionalNumberFields(rack, index, t);
    if (numberFieldError) {
      return { ok: false, error: numberFieldError };
    }

    const normalizedDevices = normalizeRoom3DDevices(rack.devices, index, t);
    if (normalizedDevices.error) {
      return { ok: false, error: normalizedDevices.error };
    }

    normalizedRacks.push({
      rack_id: rackId,
      rack_name: rackName,
      row,
      col,
      location,
      rack_type: rackType,
      rack_type_name: rackTypeName,
      u_count: rack.u_count as number | undefined,
      used_u: rack.used_u as number | undefined,
      free_u: rack.free_u as number | undefined,
      device_count: rack.device_count as number | undefined,
      unplaced_device_count: rack.unplaced_device_count as number | undefined,
      devices: normalizedDevices.devices,
    });
  }

  return {
    ok: true,
    data: {
      room: {
        id: room.id,
        name: room.name,
      },
      racks: normalizedRacks,
      notice: isNonEmptyString(value.notice) ? value.notice.trim() : undefined,
    },
  };
};
