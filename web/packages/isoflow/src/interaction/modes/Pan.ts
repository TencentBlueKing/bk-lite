import { produce } from 'immer';
import { CoordsUtils, getItemAtTile, setWindowCursor } from 'src/utils';
import { ModeActions, State } from 'src/types';
import {
  findDrawnIconId,
  findRectangleBadgeId,
  isPrimaryPointerEvent,
  regionIdForTextClick,
  resolveViewClick,
  viewHoverCursor
} from 'src/interaction/viewPointer';

const CLICK_THRESHOLD_PX = 4;

const isCanvasPointer = (state: State) => {
  if (state.isRendererInteraction) return true;

  const target = state.pointer.event.target;
  const rendererEl = state.uiState.rendererEl;

  return target instanceof Node && !!rendererEl && rendererEl.contains(target);
};

const isViewClickMode = (state: State) => {
  return (
    state.uiState.editorMode === 'EXPLORABLE_READONLY' &&
    state.callbacksRef.current.editorMode === 'EXPLORABLE_READONLY' &&
    !!state.callbacksRef.current.onItemClick
  );
};

const textRegionIdFor = (state: State) => {
  const tile = state.pointer.mouse.position.tile;
  const tileHit = getItemAtTile({ tile, scene: state.scene });
  const textRegionId =
    tileHit?.type === 'TEXTBOX'
      ? regionIdForTextClick({
          tile,
          textBoxId: tileHit.id,
          rectangles: state.scene.rectangles,
          textBoxes: state.scene.textBoxes
        })
      : null;

  return { tileHit, textRegionId };
};

const updateViewCursor = (state: State, element: HTMLElement) => {
  if (!isViewClickMode(state) || !isCanvasPointer(state)) {
    setWindowCursor('grab', element);
    return;
  }

  const point = {
    x: state.pointer.event.clientX,
    y: state.pointer.event.clientY
  };
  const iconId = findDrawnIconId(state.uiState.rendererEl, point);
  const badgeId = iconId ? null : findRectangleBadgeId(state.uiState.rendererEl, point);
  const { tileHit, textRegionId } = textRegionIdFor(state);

  setWindowCursor(
    viewHoverCursor({ badgeId, iconId, tileHit, textRegionId }),
    element
  );
};

export const Pan: ModeActions = {
  entry: (state, element) => {
    setWindowCursor('grab', element);
  },
  exit: (state, element) => {
    setWindowCursor('default', element);
  },
  mousemove: (state, element) => {
    const { uiState, panPressRef } = state;

    if (uiState.mode.type !== 'PAN') return;

    // Pan only while a canvas-armed press is held; a right-button drag stays idle.
    if (uiState.mouse.mousedown !== null && panPressRef.current) {
      const newScroll = produce(uiState.scroll, (draft) => {
        draft.position = uiState.mouse.delta?.screen
          ? CoordsUtils.add(draft.position, uiState.mouse.delta.screen)
          : draft.position;
      });

      uiState.actions.setScroll(newScroll);
      return;
    }

    updateViewCursor(state, element);
  },
  mousedown: (state, element) => {
    const { uiState, isRendererInteraction, pointer, panPressRef } = state;

    if (uiState.mode.type !== 'PAN') return;

    // The right button never arms a click or a pan.
    if (pointer.event.button === 2) {
      panPressRef.current = null;
      return;
    }

    if (!isCanvasPointer(state)) {
      panPressRef.current = null;
      return;
    }

    panPressRef.current = {
      x: pointer.mouse.position.screen.x,
      y: pointer.mouse.position.screen.y,
      button: pointer.event.button ?? 0
    };

    if (!isRendererInteraction) return;

    setWindowCursor('grabbing', element);
  },
  mouseup: (state, element) => {
    updateViewCursor(state, element);

    const { uiState, pointer, panPressRef, callbacksRef } = state;
    const press = panPressRef.current;
    panPressRef.current = null;

    if (uiState.mode.type !== 'PAN') return;
    if (!isViewClickMode(state)) return;
    if (!press || !isCanvasPointer(state)) return;
    if (press.button !== 0 || !isPrimaryPointerEvent(pointer.event)) return;

    const dx = pointer.mouse.position.screen.x - press.x;
    const dy = pointer.mouse.position.screen.y - press.y;

    if (dx * dx + dy * dy >= CLICK_THRESHOLD_PX * CLICK_THRESHOLD_PX) return;

    const onItemClick = callbacksRef.current.onItemClick;

    if (!onItemClick) return;

    const point = {
      x: pointer.event.clientX,
      y: pointer.event.clientY
    };
    const iconId = findDrawnIconId(uiState.rendererEl, point);
    const badgeId = iconId ? null : findRectangleBadgeId(uiState.rendererEl, point);
    const { tileHit, textRegionId } = textRegionIdFor(state);
    const decision = resolveViewClick({
      badgeId,
      iconId,
      tileHit,
      textRegionId
    });

    if (decision.kind === 'click') {
      onItemClick(decision.item, pointer.event);
    }
  }
};
