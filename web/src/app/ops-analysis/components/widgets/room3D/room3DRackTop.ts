import type {
  Room3DRackTopField,
  Room3DRackTopLines,
} from '@/app/ops-analysis/types/sceneWidget';
import { readRoom3DRackTopLines } from '@/app/ops-analysis/utils/room3DConfig';
import { getRoom3DPositionLabel, type Room3DRack } from './room3DData';

export const ROOM3D_RACK_TOP_LINE1_MAX_CHARS = 5;
export const ROOM3D_RACK_TOP_LINE2_MAX_CHARS = 8;

const trimText = (value: unknown): string =>
  typeof value === 'string' ? value.trim() : '';

export const getRoom3DRackTopFieldText = (
  rack: Room3DRack,
  field: Room3DRackTopField,
): string => {
  switch (field) {
    case 'location':
      return getRoom3DPositionLabel(rack);
    case 'name':
      return trimText(rack.rack_name);
    case 'type':
      return trimText(rack.rack_type_name);
    case 'state':
      return trimText(rack.rack_state_name) || readableEnumFallback(rack.rack_state);
    default:
      return '';
  }
};

const readableEnumFallback = (value: unknown): string => {
  const text = trimText(value);
  if (!text || /^\d+$/.test(text)) {
    return '';
  }
  return text;
};

export const resolveRoom3DRackTopTextureLines = (
  rack: Room3DRack,
  lines?: Room3DRackTopLines | null,
): { line1: string; line2?: string } => {
  const resolved = lines ?? readRoom3DRackTopLines();
  const line1 = getRoom3DRackTopFieldText(rack, resolved.line1).slice(
    0,
    ROOM3D_RACK_TOP_LINE1_MAX_CHARS,
  );
  if (!resolved.line2) {
    return { line1 };
  }
  const line2 = getRoom3DRackTopFieldText(rack, resolved.line2).slice(
    0,
    ROOM3D_RACK_TOP_LINE2_MAX_CHARS,
  );
  return line2 ? { line1, line2 } : { line1 };
};
