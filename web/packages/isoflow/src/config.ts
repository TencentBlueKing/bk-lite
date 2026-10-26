import {
  Size,
  InitialData,
  MainMenuOptions,
  Icon,
  Connector,
  TextBox,
  ViewItem,
  View,
  Rectangle,
  Colors,
  IsoflowLabels
} from 'src/types';
import { CoordsUtils } from 'src/utils';
import { customVars } from './styles/theme';

// TODO: This file could do with better organisation and convention for easier reading.
export const UNPROJECTED_TILE_SIZE = 100;
export const TILE_PROJECTION_MULTIPLIERS: Size = {
  width: 1.415,
  height: 0.819
};
export const PROJECTED_TILE_SIZE = {
  width: UNPROJECTED_TILE_SIZE * TILE_PROJECTION_MULTIPLIERS.width,
  height: UNPROJECTED_TILE_SIZE * TILE_PROJECTION_MULTIPLIERS.height
};

export const DEFAULT_COLOR: Colors[0] = {
  id: '__DEFAULT__',
  value: customVars.customPalette.defaultColor
};

export const DEFAULT_FONT_FAMILY = 'Roboto, Arial, sans-serif';

export const VIEW_DEFAULTS: Required<
  Omit<View, 'id' | 'description' | 'lastUpdated'>
> = {
  name: 'Untitled view',
  items: [],
  connectors: [],
  rectangles: [],
  textBoxes: []
};

export const VIEW_ITEM_DEFAULTS: Required<
  Omit<ViewItem, 'id' | 'tile' | 'bkBinding' | 'bkDisplayMetrics'>
> = {
  labelHeight: 80
};

export const CONNECTOR_DEFAULTS: Required<Omit<Connector, 'id' | 'color'>> = {
  width: 10,
  description: '',
  anchors: [],
  style: 'SOLID'
};

// The boundaries of the search area for the pathfinder algorithm
// is the grid that encompasses the two nodes + the offset below.
export const CONNECTOR_SEARCH_OFFSET = { x: 1, y: 1 };

export const TEXTBOX_DEFAULTS: Required<Omit<TextBox, 'id' | 'tile'>> = {
  orientation: 'X',
  fontSize: 0.6,
  content: 'Text'
};

export const TEXTBOX_PADDING = 0.2;
export const TEXTBOX_FONT_WEIGHT = 'bold';
// Tile units. Longer pasted titles ellipsize instead of crossing the diagram.
export const TEXTBOX_MAX_WIDTH_TILES = 4;

export const RECTANGLE_DEFAULTS: Required<
  Omit<Rectangle, 'id' | 'from' | 'to' | 'color' | 'bkFollowAlert'>
> = {};

export const ZOOM_INCREMENT = 0.2;
export const MIN_ZOOM = 0.2;
export const MAX_ZOOM = 1;
export const TRANSFORM_ANCHOR_SIZE = 30;
export const TRANSFORM_CONTROLS_COLOR = '#0392ff';
export const INITIAL_DATA: InitialData = {
  title: 'Untitled',
  version: '',
  icons: [],
  colors: [DEFAULT_COLOR],
  items: [],
  views: [],
  fitToView: false
};
export const INITIAL_UI_STATE = {
  zoom: 1,
  scroll: {
    position: CoordsUtils.zero(),
    offset: CoordsUtils.zero()
  }
};
export const INITIAL_SCENE_STATE = {
  connectors: {},
  textBoxes: {}
};
export const MAIN_MENU_OPTIONS: MainMenuOptions = [
  'ACTION.OPEN',
  'EXPORT.JSON',
  'EXPORT.PNG',
  'ACTION.CLEAR_CANVAS'
];

export const DEFAULT_ICON: Icon = {
  id: 'default',
  name: 'block',
  isIsometric: true,
  url: ''
};

/** Stored name of a newly placed icon. Hosts match on it, so it is never localized. */
export const DEFAULT_NODE_NAME = 'Untitled';

export const DEFAULT_LABELS: IsoflowLabels = {
  icon: 'Icon',
  replaceIcon: 'Replace',
  updateIcon: 'Update icon',
  nodeSettings: 'Node settings',
  settings: 'Settings',
  name: 'Name',
  description: 'Description',
  labelHeight: 'Label height',
  descriptionPlaceholder: 'Enter text...',
  delete: 'Delete',
  untitledNode: 'Untitled',
  width: 'Width',
  style: 'Style',
  styleSolid: 'Solid',
  styleDotted: 'Dotted',
  styleDashed: 'Dashed',
  textSize: 'Text size',
  alignment: 'Alignment',
  newText: 'Text',
  searchIcons: 'Search icons',
  dragHint: 'You can drag and drop any item below onto the canvas.',
  toolSelect: 'Select',
  toolPan: 'Pan',
  toolAddItem: 'Add item',
  toolRectangle: 'Rectangle',
  toolConnector: 'Connector',
  toolText: 'Text',
  toolCollapse: 'Collapse',
  toolExpand: 'Expand',
  zoomIn: 'Zoom in',
  zoomOut: 'Zoom out',
  fitToScreen: 'Fit to screen',
  sendBackward: 'Send backward',
  bringForward: 'Bring forward',
  sendToBack: 'Send to back',
  bringToFront: 'Bring to front',
  mainMenu: 'Main menu',
  open: 'Open',
  exportJson: 'Export as JSON',
  exportImage: 'Export as image',
  clearCanvas: 'Clear the canvas',
  exportBrowserWarning: 'Certain browsers may not support exporting images properly.',
  exportBrowserAdvice: 'For best results, please use the latest version of either Chrome or Firefox.',
  exportOptions: 'Options',
  showGrid: 'Show grid',
  backgroundColor: 'Background color',
  cancel: 'Cancel',
  downloadPng: 'Download as PNG',
  exportFailed: 'Could not export image',
  exportPreview: 'Preview'
};

export const DEFAULT_LABEL_HEIGHT = 20;
export const PROJECT_BOUNDING_BOX_PADDING = 3;
export const MARKDOWN_EMPTY_VALUE = '<p><br></p>';
