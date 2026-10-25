import React, { useEffect, useRef } from 'react';
import { ThemeProvider } from '@mui/material/styles';
import { Box } from '@mui/material';
import { theme } from 'src/styles/theme';
import { IsoflowProps } from 'src/types';
import { setWindowCursor, modelFromModelStore, getTilePosition, screenToIso } from 'src/utils';
import { ModelProvider, useModelStore } from 'src/stores/modelStore';
import { SceneProvider } from 'src/stores/sceneStore';
import { GlobalStyles } from 'src/styles/GlobalStyles';
import { Renderer } from 'src/components/Renderer/Renderer';
import { UiOverlay } from 'src/components/UiOverlay/UiOverlay';
import { UiStateProvider, useUiStateStore } from 'src/stores/uiStateStore';
import { INITIAL_DATA, MAIN_MENU_OPTIONS } from 'src/config';
import { useInitialDataManager } from 'src/hooks/useInitialDataManager';
import { useScene } from 'src/hooks/useScene';
import {
  DiagramOverlayProvider,
  IconPickerContext,
  ItemControlsExtraContext
} from 'src/diagramOverlay/context';
import { LabelsProvider } from 'src/hooks/useLabels';
import type { IsoflowSceneApi } from 'src/types';

const App = ({
  initialData,
  mainMenuOptions = MAIN_MENU_OPTIONS,
  width = '100%',
  height = '100%',
  onModelUpdated,
  enableDebugTools = false,
  editorMode = 'EDITABLE',
  renderer,
  enableGlobalDragHandlers = true,
  sceneApiRef
}: IsoflowProps) => {
  const uiStateActions = useUiStateStore((state) => {
    return state.actions;
  });
  const initialDataManager = useInitialDataManager();
  const modelState = useModelStore((state) => {
    return state;
  });

  const { load } = initialDataManager;

  useEffect(() => {
    load({ ...INITIAL_DATA, ...initialData });
  }, [initialData, load]);

  useEffect(() => {
    uiStateActions.setEditorMode(editorMode);
    uiStateActions.setMainMenuOptions(mainMenuOptions);
  }, [editorMode, uiStateActions, mainMenuOptions]);

  useEffect(() => {
    return () => {
      setWindowCursor('default', document.body);
    };
  }, []);

  useEffect(() => {
    if (!initialDataManager.isReady || !onModelUpdated) return;

    onModelUpdated(modelFromModelStore(modelState));
  }, [modelState, initialDataManager.isReady, onModelUpdated]);

  useEffect(() => {
    uiStateActions.setEnableDebugTools(enableDebugTools);
  }, [enableDebugTools, uiStateActions]);

  if (!initialDataManager.isReady) return null;

  return (
    <>
      <GlobalStyles />
      <Box
        sx={{
          width,
          height,
          position: 'relative',
          overflow: 'hidden',
          transform: 'translateZ(0)'
        }}
      >
        <Renderer {...renderer} enableGlobalDragHandlers={enableGlobalDragHandlers} />
        <UiOverlay />
        <SceneApiBridge sceneApiRef={sceneApiRef} />
      </Box>
    </>
  );
};

const SceneApiBridge = ({
  sceneApiRef
}: {
  sceneApiRef?: { current: IsoflowSceneApi | null };
}) => {
  const {
    updateViewItem,
    updateRectangle,
    createBoundNodes,
    items,
    rectangles
  } = useScene();
  const icons = useModelStore((state) => state.icons);
  const scroll = useUiStateStore((state) => state.scroll);
  const zoom = useUiStateStore((state) => state.zoom);
  const rendererEl = useUiStateStore((state) => state.rendererEl);
  const setScroll = useUiStateStore((state) => state.actions.setScroll);
  const updateViewItemRef = useRef(updateViewItem);
  const updateRectangleRef = useRef(updateRectangle);
  const createBoundNodesRef = useRef(createBoundNodes);
  const itemsRef = useRef(items);
  const rectanglesRef = useRef(rectangles);
  const iconsRef = useRef(icons);
  const scrollRef = useRef(scroll);
  const zoomRef = useRef(zoom);
  const rendererRef = useRef(rendererEl);
  const setScrollRef = useRef(setScroll);
  updateViewItemRef.current = updateViewItem;
  updateRectangleRef.current = updateRectangle;
  createBoundNodesRef.current = createBoundNodes;
  itemsRef.current = items;
  rectanglesRef.current = rectangles;
  iconsRef.current = icons;
  scrollRef.current = scroll;
  zoomRef.current = zoom;
  rendererRef.current = rendererEl;
  setScrollRef.current = setScroll;

  useEffect(() => {
    if (!sceneApiRef) return undefined;

    const rendererSize = () => {
      const el = rendererRef.current;
      return {
        width: el?.clientWidth ?? 0,
        height: el?.clientHeight ?? 0
      };
    };

    const screenPoint = (tile: { x: number; y: number }) => {
      const world = getTilePosition({ tile });
      const { width, height } = rendererSize();
      const current = scrollRef.current;
      return {
        x: width / 2 + current.position.x + zoomRef.current * world.x,
        y: height / 2 + current.position.y + zoomRef.current * world.y
      };
    };

    sceneApiRef.current = {
      updateViewItem: (id, updates) => updateViewItemRef.current(id, updates),
      updateRectangle: (id, updates) => updateRectangleRef.current(id, updates),
      readPlacement: () => {
        const size = rendererSize();
        const center = size.width > 0 && size.height > 0
          ? screenToIso({
            mouse: { x: size.width / 2, y: size.height / 2 },
            zoom: zoomRef.current,
            scroll: scrollRef.current,
            rendererSize: size
          })
          : { x: 0, y: 0 };
        return {
          occupied: itemsRef.current.map((item) => item.tile),
          rectangles: rectanglesRef.current.map((rectangle) => ({
            id: rectangle.id,
            from: rectangle.from,
            to: rectangle.to
          })),
          viewportCenter: center,
          iconIds: iconsRef.current.map((icon) => icon.id)
        };
      },
      createBoundNodes: (nodes) => {
        createBoundNodesRef.current(nodes);
      },
      revealTiles: (tiles) => {
        if (tiles.length === 0) return;
        const size = rendererSize();
        if (size.width <= 0 || size.height <= 0) return;
        const visible = tiles.every((tile) => {
          const point = screenPoint(tile);
          return point.x >= 0 && point.x <= size.width && point.y >= 0 && point.y <= size.height;
        });
        if (visible) return;
        const points = tiles.map((tile) => getTilePosition({ tile }));
        const world = points.reduce(
          (sum, point) => ({ x: sum.x + point.x, y: sum.y + point.y }),
          { x: 0, y: 0 }
        );
        const count = points.length;
        setScrollRef.current({
          position: {
            x: -zoomRef.current * (world.x / count),
            y: -zoomRef.current * (world.y / count)
          },
          offset: { x: 0, y: 0 }
        });
      }
    };

    return () => {
      sceneApiRef.current = null;
    };
  }, [sceneApiRef]);

  return null;
};

export const Isoflow = (props: IsoflowProps) => {
  return (
    <ThemeProvider theme={theme}>
      <ModelProvider>
        <SceneProvider>
          <UiStateProvider>
            <DiagramOverlayProvider
              onItemClick={props.onItemClick}
              onItemSelect={props.onItemSelect}
              nodeStatus={props.nodeStatus}
              nodeMetrics={props.nodeMetrics}
              nodeBinding={props.nodeBinding}
              rectangleStatus={props.rectangleStatus}
              highlightedItemId={props.highlightedItemId}
              editorMode={props.editorMode}
            >
              <LabelsProvider labels={props.labels}>
                <ItemControlsExtraContext.Provider
                  value={props.renderItemControlsExtra}
                >
                  <IconPickerContext.Provider value={props.onOpenIconPicker}>
                    <App {...props} />
                  </IconPickerContext.Provider>
                </ItemControlsExtraContext.Provider>
              </LabelsProvider>
            </DiagramOverlayProvider>
          </UiStateProvider>
        </SceneProvider>
      </ModelProvider>
    </ThemeProvider>
  );
};

const useIsoflow = () => {
  const rendererEl = useUiStateStore((state) => {
    return state.rendererEl;
  });

  const ModelActions = useModelStore((state) => {
    return state.actions;
  });

  const uiStateActions = useUiStateStore((state) => {
    return state.actions;
  });

  return {
    Model: ModelActions,
    uiState: uiStateActions,
    rendererEl
  };
};

export { useIsoflow };
export * from 'src/standaloneExports';
export default Isoflow;
