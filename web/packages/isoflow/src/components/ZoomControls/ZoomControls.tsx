import React from 'react';
import {
  Add as ZoomInIcon,
  Remove as ZoomOutIcon,
  CropFreeOutlined as FitToScreenIcon
} from '@mui/icons-material';
import { Stack, Box, Typography, Divider } from '@mui/material';
import { toPx } from 'src/utils';
import { UiElement } from 'src/components/UiElement/UiElement';
import { IconButton } from 'src/components/IconButton/IconButton';
import { MAX_ZOOM, MIN_ZOOM } from 'src/config';
import { useUiStateStore } from 'src/stores/uiStateStore';
import { useDiagramUtils } from 'src/hooks/useDiagramUtils';
import { useLabels } from 'src/hooks/useLabels';

export const ZoomControls = () => {
  const uiStateStoreActions = useUiStateStore((state) => {
    return state.actions;
  });
  const zoom = useUiStateStore((state) => {
    return state.zoom;
  });
  const { fitToView } = useDiagramUtils();
  const labels = useLabels();

  return (
    <Box sx={{ position: 'relative' }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <UiElement>
        <Stack direction="row">
          <IconButton
            name={labels.zoomOut}
            Icon={<ZoomOutIcon />}
            onClick={uiStateStoreActions.decrementZoom}
            disabled={zoom >= MAX_ZOOM}
          />
          <Divider orientation="vertical" flexItem />
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              minWidth: toPx(60)
            }}
          >
            <Typography variant="body2" color="text.secondary">
              {Math.ceil(zoom * 100)}%
            </Typography>
          </Box>
          <Divider orientation="vertical" flexItem />
          <IconButton
            name={labels.zoomIn}
            Icon={<ZoomInIcon />}
            onClick={uiStateStoreActions.incrementZoom}
            disabled={zoom <= MIN_ZOOM}
          />
        </Stack>
        </UiElement>
        <UiElement>
        <IconButton
          name={labels.fitToScreen}
          Icon={<FitToScreenIcon />}
          onClick={fitToView}
        />
        </UiElement>
      </Stack>
    </Box>
  );
};
