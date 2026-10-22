import React, { useEffect, useMemo, useRef } from 'react';
import { Box } from '@mui/material';
import { useUiStateStore } from 'src/stores/uiStateStore';
import { useInteractionManager } from 'src/interaction/useInteractionManager';
import { Grid } from 'src/components/Grid/Grid';
import { Cursor } from 'src/components/Cursor/Cursor';
import { Nodes } from 'src/components/SceneLayers/Nodes/Nodes';
import { Rectangles } from 'src/components/SceneLayers/Rectangles/Rectangles';
import { RectangleStatusLayer } from 'src/components/SceneLayers/Rectangles/RectangleStatusLayer';
import { Connectors } from 'src/components/SceneLayers/Connectors/Connectors';
import { ConnectorLabels } from 'src/components/SceneLayers/ConnectorLabels/ConnectorLabels';
import { TextBoxes } from 'src/components/SceneLayers/TextBoxes/TextBoxes';
import { SizeIndicator } from 'src/components/DebugUtils/SizeIndicator';
import { SceneLayer } from 'src/components/SceneLayer/SceneLayer';
import { TransformControlsManager } from 'src/components/TransformControlsManager/TransformControlsManager';
import { useScene } from 'src/hooks/useScene';
import { RendererProps } from 'src/types/rendererProps';

export const Renderer = ({ showGrid, backgroundColor, enableGlobalDragHandlers }: RendererProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const interactionsRef = useRef<HTMLDivElement>(null);
  const enableDebugTools = useUiStateStore((state) => {
    return state.enableDebugTools;
  });
  const mode = useUiStateStore((state) => {
    return state.mode;
  });
  const uiStateActions = useUiStateStore((state) => {
    return state.actions;
  });
  const { setInteractionsElement } = useInteractionManager(enableGlobalDragHandlers);
  const { items, rectangles, connectors, textBoxes } = useScene();

  useEffect(() => {
    if (!containerRef.current || !interactionsRef.current) return;

    setInteractionsElement(interactionsRef.current);
    uiStateActions.setRendererEl(containerRef.current);
  }, [setInteractionsElement, uiStateActions]);

  const isShowGrid = useMemo(() => {
    return showGrid === undefined || showGrid;
  }, [showGrid]);

  return (
    <Box
      ref={containerRef}
      sx={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: 0,
        bgcolor: (theme) => {
          return backgroundColor ?? theme.customVars.customPalette.diagramBg;
        }
      }}
    >
      <SceneLayer>
        <Rectangles rectangles={rectangles} />
      </SceneLayer>
      <Box
        sx={{
          position: 'absolute',
          width: '100%',
          height: '100%',
          top: 0,
          left: 0
        }}
      >
        {isShowGrid && <Grid />}
      </Box>
      {mode.showCursor && (
        <SceneLayer>
          <Cursor />
        </SceneLayer>
      )}
      <SceneLayer>
        <Connectors connectors={connectors} />
      </SceneLayer>
      <SceneLayer>
        <TextBoxes textBoxes={textBoxes} />
      </SceneLayer>
      <SceneLayer>
        <ConnectorLabels connectors={connectors} />
      </SceneLayer>
      {enableDebugTools && (
        <SceneLayer>
          <SizeIndicator />
        </SceneLayer>
      )}
      {/* Interaction layer: this is where events are detected */}
      <Box
        ref={interactionsRef}
        sx={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: '100%',
          height: '100%'
        }}
      />
      {/*
        Area alert labels lie on the ground under icons, so an icon or name
        plate on the corner tile stays visible and wins the click. The layer
        sits above the interaction layer so the label still gets hover and its
        native tooltip.
      */}
      <SceneLayer>
        <RectangleStatusLayer />
      </SceneLayer>
      <SceneLayer>
        <Nodes nodes={items} />
      </SceneLayer>
      <SceneLayer order={2}>
        <TransformControlsManager />
      </SceneLayer>
    </Box>
  );
};
