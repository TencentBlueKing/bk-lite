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
    <UiElement sx={{ borderRadius: '8px' }}>
      <Stack
        direction="row"
        sx={{
          height: 32,
          alignItems: 'center',
          '& .MuiButton-root': {
            width: 32,
            height: 32,
            minWidth: 32,
            borderRadius: 0
          },
          '& .MuiSvgIcon-root': {
            width: 16,
            height: 16
          }
        }}
      >
        <IconButton
          name={labels.zoomOut}
          Icon={<ZoomOutIcon />}
          onClick={uiStateStoreActions.decrementZoom}
          disabled={zoom >= MAX_ZOOM}
          size={32}
        />
        <Divider orientation="vertical" flexItem />
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minWidth: toPx(44),
            px: 0.5
          }}
        >
          <Typography sx={{ fontSize: 12, lineHeight: 1, color: 'var(--color-text-2)' }}>
            {Math.ceil(zoom * 100)}%
          </Typography>
        </Box>
        <Divider orientation="vertical" flexItem />
        <IconButton
          name={labels.zoomIn}
          Icon={<ZoomInIcon />}
          onClick={uiStateStoreActions.incrementZoom}
          disabled={zoom <= MIN_ZOOM}
          size={32}
        />
        <Divider orientation="vertical" flexItem />
        <IconButton
          name={labels.fitToScreen}
          Icon={<FitToScreenIcon />}
          onClick={fitToView}
          size={32}
        />
      </Stack>
    </UiElement>
  );
};
