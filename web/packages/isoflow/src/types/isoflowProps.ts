import type { ReactNode } from 'react';
import type { EditorModeEnum, MainMenuOptions } from './common';
import type { IsoflowLabels } from './labels';
import type { Model, Rectangle, ViewItem } from './model';
import type { RendererProps } from './rendererProps';

export type InitialData = Model & {
  fitToView?: boolean;
  view?: string;
};

export const nodeStatusLevels = [
  'normal',
  'warning',
  'critical',
  'unmonitored',
  'unknown',
  'invalid',
  'forbidden'
] as const;

export type NodeStatusLevel = (typeof nodeStatusLevels)[number];

export interface NodeMetricLine {
  name: string;
  text: string;
}

/** View mode. The host already chose the lines and formatted the values. */
export interface NodeMetrics {
  lines: NodeMetricLine[];
  /**
   * True: the lines stay under the name. False: they appear only while the
   * name card is hovered, together with the model and alert lines.
   */
  pinned?: boolean;
}

export interface NodeStatus {
  /** Omitted in edit mode, where the plate is a name and not a runtime status. */
  level?: NodeStatusLevel;
  count?: number;
  /** Hover text for a gray status mark. The host supplies the localized sentence. */
  hint?: string;
  /** Hover text for the alert-count badge. */
  badgeHint?: string;
  /**
   * Short mark on the name plate. View mode only. The host supplies the
   * localized text. A warning or critical alert count is drawn as a badge on
   * the plate's top-right corner; a short label such as unmonitored, unknown,
   * or no permission stays to the right of the name. A normal level draws a
   * floor-wash-colored dot to the right of the name instead of text.
   */
  plateMark?: string;
  /** Replaces the icon title when the icon name is empty or the default Untitled. */
  plateTitle?: string;
  /** Second line under the icon name. Hidden by the scene when zoom is below 70%. */
  plateSubtitle?: string;
  /** Bound resource name is not drawn. Model may appear as a suffix on the title. */
  hoverName?: string;
  hoverModel?: string;
  /** Label drawn before the model name when the plate is expanded. Host supplies the localized word, including its colon. */
  hoverModelLabel?: string;
  /** Label drawn before the status sentence when the plate is expanded. */
  hoverStatusLabel?: string;
  /** Status sentence drawn under the model when the plate is expanded. */
  hoverAlert?: string;
}

/** Edit-mode binding marks. These are not status and must not carry alert color. */
export interface NodeBindingMark {
  unbound?: boolean;
}

export const rectangleBorderLevels = ['warning', 'critical', 'unknown'] as const;

export type RectangleBorderLevel = (typeof rectangleBorderLevels)[number];

export interface RectangleStatus {
  label?: string;
  borderLevel?: RectangleBorderLevel;
  /** Highest active alert level; sets the colour of the area alert label. */
  badgeLevel?: 'critical' | 'warning';
  /**
   * Number on the area alert label: the area's deduped active alert total
   * (severe + warning). No label is drawn when it is missing or zero.
   */
  badgeCount?: number;
  /** Hover text for the area alert label, such as the level breakdown. Host supplies the localized text. */
  badgeHint?: string;
}

export type ItemControlsExtraTarget = {
  type: 'ITEM' | 'RECTANGLE';
  id: string;
};

/** Icon the host draws inside its own picker dialog. */
export interface IconPickerIcon {
  id: string;
  name: string;
  url: string;
}

/** Edit mode. The host opens its dialog; selecting an icon updates the node. */
export interface IconPickerRequest {
  title: string;
  icons: IconPickerIcon[];
  onSelect: (iconId: string) => void;
}

export type DiagramItemHit = {
  type: 'ITEM' | 'RECTANGLE' | 'CONNECTOR';
  id: string;
};

export type DiagramPointerEvent = {
  clientX: number;
  clientY: number;
};

export interface IsoflowProps {
  initialData?: InitialData;
  mainMenuOptions?: MainMenuOptions;
  onModelUpdated?: (Model: Model) => void;
  width?: number | string;
  height?: number | string;
  enableDebugTools?: boolean;
  editorMode?: keyof typeof EditorModeEnum;
  renderer?: RendererProps;
  /**
   * Controls whether drag interactions are captured globally (window-level) or limited to the frame.
   * 
   * - `true` (default): Drag events are captured globally, allowing dragging even when the mouse moves outside the component
   * - `false`: Drag events are limited to the component frame, useful for embedding in other pages
   * 
   * @default true
   */
  enableGlobalDragHandlers?: boolean;
  /**
   * View mode only (`EXPLORABLE_READONLY`). Fired on a click, not a pan.
   * `null` means empty canvas, so the host can close a detail view.
   * Text boxes are not reported.
   */
  onItemClick?: (
    item: DiagramItemHit | null,
    event?: DiagramPointerEvent
  ) => void;
  /**
   * Edit mode only. Fired when cursor mode opens item, rectangle or connector
   * controls, and with `null` when the selection is cleared.
   */
  onItemSelect?: (item: DiagramItemHit | null) => void;
  /** View mode. Neutral stroke around one icon. Keyed by view item id. */
  highlightedItemId?: string;
  /** Keyed by view item id. Icons omitted from the map are drawn unchanged. */
  nodeStatus?: Record<string, NodeStatus>;
  /** View mode. Keyed by view item id. Drawn under the name in the name card. */
  nodeMetrics?: Record<string, NodeMetrics>;
  /**
   * Edit mode. Keyed by view item id. An unbound diamond is drawn only for ids
   * present in the map, and only while the host asks for that highlight.
   */
  nodeBinding?: Record<string, NodeBindingMark>;
  /** Keyed by rectangle id. Labels, borders and badges are draw-only. */
  rectangleStatus?: Record<string, RectangleStatus>;
  /**
   * Edit mode. Calls the existing single-item updaters so a binding change
   * goes through onModelUpdated without replacing initialData.
   */
  sceneApiRef?: { current: IsoflowSceneApi | null };
  /**
   * Edit mode. Host content for the settings panels: for an icon, a single-line
   * strip (28px, full width) at the bottom of the header, which keeps its
   * original height; for an area, content at the top of the panel.
   */
  renderItemControlsExtra?: (item: ItemControlsExtraTarget) => ReactNode;
  /**
   * Edit mode. Opens the host's icon picker instead of a scene dialog.
   * The host owns the modal chrome and calls `onSelect` when an icon is chosen.
   */
  onOpenIconPicker?: (request: IconPickerRequest) => void;
  /** Localized editor text. Missing keys fall back to English. */
  labels?: Partial<IsoflowLabels>;
}

export interface ArchitectureTile {
  x: number;
  y: number;
}

export interface ArchitecturePlacement {
  occupied: ArchitectureTile[];
  rectangles: { id: string; from: ArchitectureTile; to: ArchitectureTile }[];
  viewportCenter: ArchitectureTile;
  iconIds: string[];
}

export interface ArchitectureBoundNode {
  id: string;
  name: string;
  icon: string;
  tile: ArchitectureTile;
  bkBinding: { inst_uuid: string; model_id: string };
}

export interface IsoflowSceneApi {
  updateViewItem: (id: string, updates: Partial<ViewItem>) => void;
  updateRectangle: (id: string, updates: Partial<Rectangle>) => void;
  /** Current view tiles, areas, viewport center, and icon ids. */
  readPlacement: () => ArchitecturePlacement;
  /** Adds bound icons on the current view. Does not draw connectors or areas. */
  createBoundNodes: (nodes: ArchitectureBoundNode[]) => void;
  /** Pans so the tiles are in view when any of them is outside the canvas. */
  revealTiles: (tiles: ArchitectureTile[]) => void;
}
