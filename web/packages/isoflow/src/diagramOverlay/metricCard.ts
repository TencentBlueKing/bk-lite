/** Pinned lines stay in the name card from 70% zoom up. Hover still shows them below that. */
export const METRIC_CARD_MIN_ZOOM = 0.7;

export function visibleMetricLines(input: {
  editorMode: string;
  zoom: number;
  pinned: boolean;
  hovering: boolean;
  lineCount: number;
}): boolean {
  if (input.editorMode === 'EDITABLE' || input.lineCount <= 0) return false;
  if (input.hovering) return true;
  return input.pinned && input.zoom >= METRIC_CARD_MIN_ZOOM;
}
