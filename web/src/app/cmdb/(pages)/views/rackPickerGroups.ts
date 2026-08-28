export interface RackPickerRack {
  inst_uuid: string;
  inst_name: string;
  model_id?: string;
}

export interface RackPickerRoomGroup {
  room_uuid: string | null;
  room_name: string;
  racks: RackPickerRack[];
}

export interface RackPickerSelectOption {
  label: string;
  value: string;
  selectedLabel: string;
}

export interface RackPickerSelectGroup {
  label: string;
  options: RackPickerSelectOption[];
}

const roomKey = (roomUuid: string | null | undefined) => roomUuid || '';

export const mergeRackRoomGroups = (
  prev: RackPickerRoomGroup[],
  next: RackPickerRoomGroup[],
  append: boolean
): RackPickerRoomGroup[] => {
  if (!append) return next;
  const merged = prev.map((group) => ({
    ...group,
    racks: [...group.racks],
  }));
  const indexByKey = new Map(
    merged.map((group, index) => [roomKey(group.room_uuid), index])
  );
  for (const group of next) {
    const key = roomKey(group.room_uuid);
    const existingIndex = indexByKey.get(key);
    if (existingIndex == null) {
      indexByKey.set(key, merged.length);
      merged.push({
        ...group,
        racks: [...group.racks],
      });
      continue;
    }
    const existing = merged[existingIndex];
    const seen = new Set(existing.racks.map((rack) => rack.inst_uuid));
    for (const rack of group.racks) {
      if (seen.has(rack.inst_uuid)) continue;
      existing.racks.push(rack);
      seen.add(rack.inst_uuid);
    }
  }
  return merged;
};

const formatRackWithRoom = (
  template: string,
  roomName: string,
  rackName: string
) => template.replace('{room}', roomName).replace('{rack}', rackName);

export const rackGroupsToSelectOptions = ({
  recent,
  groups,
  selected,
  keyword,
  recentLabel,
  unassociatedLabel,
  rackWithRoom,
}: {
  recent: { inst_uuid: string; inst_name?: string }[];
  groups: RackPickerRoomGroup[];
  selected: { inst_uuid: string; inst_name?: string }[];
  keyword: string;
  recentLabel: string;
  unassociatedLabel: string;
  rackWithRoom: string;
}): RackPickerSelectGroup[] => {
  const result: RackPickerSelectGroup[] = [];
  const recentIds = new Set(keyword ? [] : recent.map((item) => item.inst_uuid));

  if (recent.length > 0 && !keyword) {
    result.push({
      label: recentLabel,
      options: recent.map((item) => {
        const name = item.inst_name || item.inst_uuid;
        return {
          label: name,
          value: item.inst_uuid,
          selectedLabel: name,
        };
      }),
    });
  }

  const listedIds = new Set(recentIds);
  for (const group of groups) {
    const roomName = group.room_name || unassociatedLabel;
    const options = group.racks
      .filter((rack) => !recentIds.has(rack.inst_uuid))
      .map((rack) => {
        listedIds.add(rack.inst_uuid);
        const rackName = rack.inst_name || rack.inst_uuid;
        return {
          label: rackName,
          value: rack.inst_uuid,
          selectedLabel: formatRackWithRoom(rackWithRoom, roomName, rackName),
        };
      });
    if (!options.length) continue;
    result.push({
      label: roomName,
      options,
    });
  }

  const missingSelected = selected.filter(
    (item) => !listedIds.has(item.inst_uuid)
  );
  if (missingSelected.length) {
    result.unshift({
      label: '\u200B',
      options: missingSelected.map((item) => {
        const name = item.inst_name || item.inst_uuid;
        return {
          label: name,
          value: item.inst_uuid,
          selectedLabel: name,
        };
      }),
    });
  }

  return result;
};
