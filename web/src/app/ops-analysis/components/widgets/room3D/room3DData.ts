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

export type Room3DAlarmSeverity = 'critical' | 'error' | 'warning';

export interface Room3DDevice {
  device_id: string;
  device_name: string;
  model_id?: string | null;
  rack_u_start?: number | null;
  u_size?: number | null;
  status?: string | null;
  /** false / missing → treat as unbound for backward compatibility */
  monitor_bound?: boolean;
  alarm_unavailable?: boolean;
  active_alarm_count?: number | null;
  highest_severity?: Room3DAlarmSeverity | null;
}

export type Room3DRenderableDevice = Room3DDevice;

export interface Room3DRackAlarmSummary {
  count: number;
  highest_severity: Room3DAlarmSeverity | null;
}

const ROOM3D_ALARM_SEVERITIES: readonly Room3DAlarmSeverity[] = [
  'critical',
  'error',
  'warning',
];

const ROOM3D_SEVERITY_RANK: Record<Room3DAlarmSeverity, number> = {
  critical: 3,
  error: 2,
  warning: 1,
};

const isRoom3DAlarmSeverity = (value: unknown): value is Room3DAlarmSeverity =>
  typeof value === 'string' &&
  (ROOM3D_ALARM_SEVERITIES as readonly string[]).includes(value);

const normalizeRoom3DAlarmFields = (
  device: Record<string, unknown>,
): Pick<
  Room3DDevice,
  'monitor_bound' | 'alarm_unavailable' | 'active_alarm_count' | 'highest_severity'
> => {
  const monitor_bound = device.monitor_bound === true;
  const alarm_unavailable = device.alarm_unavailable === true;

  let active_alarm_count: number | null = null;
  if (
    typeof device.active_alarm_count === 'number' &&
    Number.isInteger(device.active_alarm_count) &&
    device.active_alarm_count >= 0
  ) {
    active_alarm_count = device.active_alarm_count;
  }

  const highest_severity = isRoom3DAlarmSeverity(device.highest_severity)
    ? device.highest_severity
    : null;

  // Coerce to Spec four-state table; reject illegal combinations.
  if (alarm_unavailable) {
    return {
      monitor_bound,
      alarm_unavailable: true,
      active_alarm_count: null,
      highest_severity: null,
    };
  }
  if (!monitor_bound) {
    return {
      monitor_bound: false,
      alarm_unavailable: false,
      active_alarm_count: null,
      highest_severity: null,
    };
  }
  if (active_alarm_count === null) {
    return {
      monitor_bound: true,
      alarm_unavailable: true,
      active_alarm_count: null,
      highest_severity: null,
    };
  }
  if (active_alarm_count <= 0) {
    return {
      monitor_bound: true,
      alarm_unavailable: false,
      active_alarm_count: 0,
      highest_severity: null,
    };
  }
  return {
    monitor_bound: true,
    alarm_unavailable: false,
    active_alarm_count,
    highest_severity,
  };
};

/** Glow only for available devices with a positive active alarm count. */
export const deviceHasAlarmGlow = (
  device: Pick<Room3DDevice, 'active_alarm_count'> &
    Partial<Pick<Room3DDevice, 'alarm_unavailable'>>,
): boolean =>
  device.alarm_unavailable !== true &&
  typeof device.active_alarm_count === 'number' &&
  device.active_alarm_count > 0;

export const formatRoom3DSeverityLabel = (
  severity: Room3DAlarmSeverity | null | undefined,
  translate: (id: string) => string,
): string => {
  if (!severity) {
    return '';
  }
  return translate(`dashboard.application3DSeverity_${severity}`);
};

/** Sidebar active-alarm value for the four Spec states. */
export const formatRoom3DDeviceAlarmCountValue = (
  device: Pick<
    Room3DDevice,
    'monitor_bound' | 'alarm_unavailable' | 'active_alarm_count'
  >,
  translate: (id: string) => string,
): string => {
  if (device.alarm_unavailable) {
    return translate('dashboard.room3DAlarmUnavailable');
  }
  if (!device.monitor_bound) {
    return translate('dashboard.room3DMonitorUnbound');
  }
  const count = device.active_alarm_count ?? 0;
  if (count <= 0) {
    return translate('dashboard.room3DNoAlarms');
  }
  return `${count}${translate('dashboard.room3DCountUnit')}`;
};

/** Second sidebar row: highest severity only when bound, available, and count > 0. */
export const shouldShowRoom3DDeviceHighestSeverity = (
  device: Pick<
    Room3DDevice,
    | 'monitor_bound'
    | 'alarm_unavailable'
    | 'active_alarm_count'
    | 'highest_severity'
  >,
): boolean =>
  !device.alarm_unavailable &&
  device.monitor_bound === true &&
  (device.active_alarm_count ?? 0) > 0 &&
  isRoom3DAlarmSeverity(device.highest_severity);

export const aggregateRackAlarmSummary = (
  devices: ReadonlyArray<
    Pick<Room3DDevice, 'active_alarm_count' | 'highest_severity'> &
      Partial<Room3DDevice>
  >,
): Room3DRackAlarmSummary => {
  let count = 0;
  let highest_severity: Room3DAlarmSeverity | null = null;
  let highestRank = 0;

  devices.forEach((device) => {
    if (
      device.alarm_unavailable === true ||
      typeof device.active_alarm_count !== 'number' ||
      !Number.isFinite(device.active_alarm_count)
    ) {
      // null / unavailable contribute neither count nor severity
    } else {
      count += device.active_alarm_count;
    }
    if (
      !deviceHasAlarmGlow(device) ||
      !isRoom3DAlarmSeverity(device.highest_severity)
    ) {
      return;
    }
    const rank = ROOM3D_SEVERITY_RANK[device.highest_severity];
    if (rank > highestRank) {
      highestRank = rank;
      highest_severity = device.highest_severity;
    }
  });

  return { count, highest_severity };
};

export type Room3DValidationResult =
  | { ok: true; data: Room3DResponse }
  | { ok: false; error: string };

export type Room3DTranslator = (id: string) => string;

export interface Room3DDisplayOptions {
  immersive: boolean;
}

export const getRoom3DDisplayOptions = (config?: {
  appearance?: { frame?: string };
}): Room3DDisplayOptions => {
  const immersive = config?.appearance?.frame === 'bare';
  return { immersive };
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

const ROOM3D_LOCATION_PATTERN = /^([A-Z]+)(\d+)$/i;

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
      ...normalizeRoom3DAlarmFields(device),
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

export const getRoom3DRowLabel = (row: number) => {
  if (!Number.isInteger(row) || row < 1) {
    return '';
  }
  return String(row);
};

export const getRoom3DStandardLocation = (row: number, col: number) => {
  // 机房实物约定：一整排同一字母（行），过道方向 01、02、03（列）
  const rowLabel = getRoom3DColumnLabel(row);
  if (!rowLabel || !Number.isInteger(col) || col < 1) {
    return '';
  }
  return `${rowLabel}${String(col).padStart(2, '0')}`;
};

const parseRoom3DLocation = (value: unknown) => {
  if (!isNonEmptyString(value)) {
    return null;
  }
  const match = ROOM3D_LOCATION_PATTERN.exec(value.trim());
  if (!match) {
    return null;
  }

  const row = match[1]
    .toUpperCase()
    .split('')
    .reduce((total, char) => total * 26 + char.charCodeAt(0) - 64, 0);
  const col = Number.parseInt(match[2], 10);
  if (!Number.isInteger(row) || row < 1 || !Number.isInteger(col) || col < 1) {
    return null;
  }
  return { row, col, location: getRoom3DStandardLocation(row, col) };
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
    const parsedLocation = parseRoom3DLocation(rack.location);
    const row = parsedLocation?.row ?? rack.row;
    const col = parsedLocation?.col ?? rack.col;
    const location = parsedLocation?.location ?? getRoom3DStandardLocation(row, col);
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
