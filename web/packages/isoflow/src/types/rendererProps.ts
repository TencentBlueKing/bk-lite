export interface RendererProps {
  showGrid?: boolean;
  backgroundColor?: string;
  /**
   * Controls whether drag interactions are captured globally (window-level) or limited to the frame.
   * 
   * - `true` (default): Drag events are captured globally, allowing dragging even when the mouse moves outside the component
   * - `false`: Drag events are limited to the component frame, useful for embedding in other pages
   * 
   * @default true
   */
  enableGlobalDragHandlers?: boolean;
}
