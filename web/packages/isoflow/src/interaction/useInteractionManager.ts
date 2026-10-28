import { useCallback, useEffect, useRef } from 'react';
import { useModelStore } from 'src/stores/modelStore';
import { useUiStateStore } from 'src/stores/uiStateStore';
import { ModeActions, PanPress, State, SlimMouseEvent } from 'src/types';
import { useDiagramCallbacksRef } from 'src/diagramOverlay/context';
import { getMouse, getItemAtTile } from 'src/utils';
import { useResizeObserver } from 'src/hooks/useResizeObserver';
import { useScene } from 'src/hooks/useScene';
import { Cursor } from './modes/Cursor';
import { DragItems } from './modes/DragItems';
import { DrawRectangle } from './modes/Rectangle/DrawRectangle';
import { TransformRectangle } from './modes/Rectangle/TransformRectangle';
import { Connector } from './modes/Connector';
import { Pan } from './modes/Pan';
import { PlaceIcon } from './modes/PlaceIcon';
import { TextBox } from './modes/TextBox';

const modes: { [k in string]: ModeActions } = {
  CURSOR: Cursor,
  DRAG_ITEMS: DragItems,
  // TODO: Adopt this notation for all modes (i.e. {node.type}.{action})
  'RECTANGLE.DRAW': DrawRectangle,
  'RECTANGLE.TRANSFORM': TransformRectangle,
  CONNECTOR: Connector,
  PAN: Pan,
  PLACE_ICON: PlaceIcon,
  TEXTBOX: TextBox
};

const getModeFunction = (mode: ModeActions, e: SlimMouseEvent) => {
  switch (e.type) {
    case 'mousemove':
    case 'pointermove':
      return mode.mousemove;
    case 'mousedown':
    case 'pointerdown':
      return mode.mousedown;
    case 'mouseup':
    case 'pointerup':
      return mode.mouseup;
    default:
      return null;
  }
};

export const useInteractionManager = (enableGlobalDragHandlers: boolean = true) => {
  const rendererRef = useRef<HTMLElement | null>(null);
  const reducerTypeRef = useRef<string | null>(null);
  const panPressRef = useRef<PanPress | null>(null);
  const callbacksRef = useDiagramCallbacksRef();
  const uiState = useUiStateStore((state) => {
    return state;
  });
  const model = useModelStore((state) => {
    return state;
  });
  const scene = useScene();
  const { size: rendererSize } = useResizeObserver(uiState.rendererEl);
  const el = enableGlobalDragHandlers ? window : (rendererRef.current || uiState.rendererEl) as unknown as Window;
  const elCursor = enableGlobalDragHandlers ? document.body : (rendererRef.current || uiState.rendererEl) as HTMLElement;

  const onMouseEvent = useCallback(
    (e: SlimMouseEvent) => {
      if (e.type === 'pointerdown') {
        if (e.target instanceof HTMLElement) {
          e.target.setPointerCapture((e as unknown as PointerEvent).pointerId);
        }
      }
      if (e.type === 'pointerup') {
        if (e.target instanceof HTMLElement) {
          e.target.releasePointerCapture((e as unknown as PointerEvent).pointerId);
        }
      }

      if (!rendererRef.current) return;

      const mode = modes[uiState.mode.type];
      const modeFunction = getModeFunction(mode, e);
      if (!modeFunction) return;

      const nextMouse = getMouse({
        interactiveElement: rendererRef.current,
        zoom: uiState.zoom,
        scroll: uiState.scroll,
        lastMouse: uiState.mouse,
        mouseEvent: e,
        rendererSize
      });
      uiState.actions.setMouse(nextMouse);

      const baseState: State = {
        model,
        scene,
        uiState,
        rendererRef: rendererRef.current,
        rendererSize,
        isRendererInteraction: rendererRef.current === e.target,
        pointer: {
          mouse: nextMouse,
          event: e
        },
        panPressRef,
        callbacksRef
      };

      if (reducerTypeRef.current !== uiState.mode.type) {
        const prevReducer = reducerTypeRef.current
          ? modes[reducerTypeRef.current]
          : null;
        if (prevReducer && prevReducer.exit) {
          prevReducer.exit(baseState, elCursor);
        }
        if (mode.entry) {
          mode.entry(baseState, elCursor);
        }
      }
      modeFunction(baseState, elCursor);
      reducerTypeRef.current = uiState.mode.type;
    },
    [model, scene, uiState, rendererSize, callbacksRef]
  );

  const onContextMenu = useCallback(
    (e: SlimMouseEvent) => {
      const itemAtTile = getItemAtTile({
        tile: uiState.mouse.position.tile,
        scene
      });
      // Edit mode still uses the layer-order menu on areas. Everywhere else,
      // including view mode, the browser menu stays available.
      if (uiState.editorMode === 'EDITABLE' && itemAtTile?.type === 'RECTANGLE') {
        e.preventDefault();
        uiState.actions.setContextMenu({
          item: itemAtTile,
          tile: uiState.mouse.position.tile
        });
        return;
      }

      if (uiState.contextMenu) {
        uiState.actions.setContextMenu(null);
      }
    },
    [uiState.mouse, scene, uiState.contextMenu, uiState.actions, uiState.editorMode]
  );

  useEffect(() => {
    if (uiState.mode.type === 'INTERACTIONS_DISABLED') return;

    // Choose the element to attach event listeners to based on the enableGlobalDragHandlers setting
    if (!el) return;

    const onTouchStart = (e: TouchEvent) => {
      onMouseEvent({
        ...e,
        clientX: Math.floor(e.touches[0].clientX),
        clientY: Math.floor(e.touches[0].clientY),
        type: 'mousedown'
      });
    };
    const onTouchMove = (e: TouchEvent) => {
      onMouseEvent({
        ...e,
        clientX: Math.floor(e.touches[0].clientX),
        clientY: Math.floor(e.touches[0].clientY),
        type: 'mousemove'
      });
    };
    const onTouchEnd = (e: TouchEvent) => {
      onMouseEvent({
        ...e,
        clientX: 0,
        clientY: 0,
        type: 'mouseup'
      });
    };
    const onScroll = (e: WheelEvent) => {
      if (e.deltaY > 0) {
        uiState.actions.decrementZoom();
      } else {
        uiState.actions.incrementZoom();
      }
    };

    el.addEventListener('pointermove', onMouseEvent);
    el.addEventListener('pointerdown', onMouseEvent);
    el.addEventListener('pointerup', onMouseEvent);
    el.addEventListener('contextmenu', onContextMenu);
    // el.addEventListener('touchstart', onTouchStart);
    // el.addEventListener('touchmove', onTouchMove);
    // el.addEventListener('touchend', onTouchEnd);
    uiState.rendererEl?.addEventListener('wheel', onScroll);

    return () => {
      el.removeEventListener('pointermove', onMouseEvent);
      el.removeEventListener('pointerdown', onMouseEvent);
      el.removeEventListener('pointerup', onMouseEvent);
      el.removeEventListener('contextmenu', onContextMenu);
      // el.removeEventListener('touchstart', onTouchStart);
      // el.removeEventListener('touchmove', onTouchMove);
      // el.removeEventListener('touchend', onTouchEnd);
      uiState.rendererEl?.removeEventListener('wheel', onScroll);
    };
  }, [
    uiState.editorMode,
    onMouseEvent,
    uiState.mode.type,
    onContextMenu,
    uiState.actions,
    uiState.rendererEl,
    enableGlobalDragHandlers
  ]);

  const setInteractionsElement = useCallback((element: HTMLElement) => {
    rendererRef.current = element;
  }, []);

  return {
    setInteractionsElement
  };
};
