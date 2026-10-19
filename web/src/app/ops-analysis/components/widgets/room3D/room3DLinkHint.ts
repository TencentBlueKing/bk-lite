import type { InteractionSurface } from "@/app/ops-analysis/utils/interactionLink";
import { shouldShowContextLinkHint } from "@/app/ops-analysis/utils/interactionLinkHint";
import {
  canOpenRoom3DRackLink,
  type Room3DRack,
} from "./room3DData";

/** 设备悬停提示：查看态数据链接，且机柜不是冲突占位。 */
export const shouldShowRoom3DDeviceLinkHint = (
  surface: InteractionSurface,
  link: { kind?: string } | null | undefined,
  rack: Pick<Room3DRack, "is_conflict"> | null | undefined,
  device: { device_id?: string } | null | undefined,
) =>
  Boolean(device) &&
  Boolean(rack) &&
  shouldShowContextLinkHint(
    surface,
    link,
    rack ? canOpenRoom3DRackLink(rack) : false,
  );
