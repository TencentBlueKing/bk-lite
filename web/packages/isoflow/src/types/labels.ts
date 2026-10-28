/** User-visible editor text. The host passes localized values; English is the default. */
export interface IsoflowLabels {
  // Icon settings
  /** Section title above the icon thumbnail. */
  icon: string;
  /** Hover mask on the icon thumbnail. */
  replaceIcon: string;
  updateIcon: string;
  /** Title of the node settings panel. */
  nodeSettings: string;
  settings: string;
  name: string;
  description: string;
  labelHeight: string;
  descriptionPlaceholder: string;
  delete: string;
  /** Shown for an icon whose stored name is the default `Untitled`. */
  untitledNode: string;
  // Connector settings
  width: string;
  style: string;
  styleSolid: string;
  styleDotted: string;
  styleDashed: string;
  // Text settings
  textSize: string;
  alignment: string;
  /** Content of a new text box. */
  newText: string;
  // Icon picker
  searchIcons: string;
  dragHint: string;
  // Tool menu
  toolSelect: string;
  toolPan: string;
  toolAddItem: string;
  toolRectangle: string;
  toolConnector: string;
  toolText: string;
  toolCollapse: string;
  toolExpand: string;
  // Zoom
  zoomIn: string;
  zoomOut: string;
  fitToScreen: string;
  // Layer order menu
  sendBackward: string;
  bringForward: string;
  sendToBack: string;
  bringToFront: string;
  // Main menu
  mainMenu: string;
  open: string;
  exportJson: string;
  exportImage: string;
  clearCanvas: string;
  // Export image dialog
  exportBrowserWarning: string;
  exportBrowserAdvice: string;
  exportOptions: string;
  showGrid: string;
  backgroundColor: string;
  cancel: string;
  downloadPng: string;
  exportFailed: string;
  exportPreview: string;
}
