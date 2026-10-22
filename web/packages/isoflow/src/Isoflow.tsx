import React, { useEffect, useRef } from 'react';
import { ThemeProvider } from '@mui/material/styles';
import { Box } from '@mui/material';
import { theme } from 'src/styles/theme';
import { IsoflowProps } from 'src/types';
import { setWindowCursor, modelFromModelStore } from 'src/utils';
import { useModelStore, ModelProvider } from 'src/stores/modelStore';
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
  const { updateViewItem, updateRectangle } = useScene();
  const updateViewItemRef = useRef(updateViewItem);
  const updateRectangleRef = useRef(updateRectangle);
  updateViewItemRef.current = updateViewItem;
  updateRectangleRef.current = updateRectangle;

  useEffect(() => {
    if (!sceneApiRef) return undefined;

    sceneApiRef.current = {
      updateViewItem: (id, updates) => updateViewItemRef.current(id, updates),
      updateRectangle: (id, updates) => updateRectangleRef.current(id, updates)
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
              nodeBinding={props.nodeBinding}
              rectangleStatus={props.rectangleStatus}
              highlightedItemId={props.highlightedItemId}
              editorMode={props.editorMode}
            >
              <LabelsProvider labels={props.labels}>
                <ItemControlsExtraContext.Provider
                  value={props.renderItemControlsExtra}
                >
                  <App {...props} />
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
