import { ModelStore, UiStateStore, Size, Mouse, SlimMouseEvent } from 'src/types';
import { useScene } from 'src/hooks/useScene';
import type { DiagramCallbacksRef } from 'src/diagramOverlay/callbacks';

export interface PanPress {
  x: number;
  y: number;
  /** MouseEvent.button that started the press. Only a primary-button press may end as a click. */
  button: number;
}

export interface State {
  model: ModelStore;
  scene: ReturnType<typeof useScene>;
  uiState: UiStateStore;
  rendererRef: HTMLElement;
  rendererSize: Size;
  isRendererInteraction: boolean;
  pointer: {
    mouse: Mouse;
    event: SlimMouseEvent;
  };
  panPressRef: { current: PanPress | null };
  callbacksRef: DiagramCallbacksRef;
}

export type ModeActionsAction = (state: State) => void;
export type ModeActionsActionWithElement = (state: State, element: HTMLElement) => void;

export type ModeActions = {
  entry?: ModeActionsActionWithElement;
  exit?: ModeActionsActionWithElement;
  mousemove?: ModeActionsActionWithElement;
  mousedown?: ModeActionsActionWithElement;
  mouseup?: ModeActionsActionWithElement;
};
