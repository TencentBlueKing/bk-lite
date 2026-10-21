import React, { useState, useCallback } from 'react';
import { Box, Stack, Button } from '@mui/material';
import {
  ChevronRight as ChevronRightIcon,
  ChevronLeft as ChevronLeftIcon
} from '@mui/icons-material';
import { useIconCategories } from 'src/hooks/useIconCategories';
import { useIcon } from 'src/hooks/useIcon';
import { useScene } from 'src/hooks/useScene';
import { useViewItem } from 'src/hooks/useViewItem';
import { useUiStateStore } from 'src/stores/uiStateStore';
import { useModelItem } from 'src/hooks/useModelItem';
import { useLabels } from 'src/hooks/useLabels';
import { useItemControlsExtra } from 'src/diagramOverlay/context';
import { ControlsContainer } from '../components/ControlsContainer';
import { Icons } from '../IconSelectionControls/Icons';
import { NodeSettings } from './NodeSettings/NodeSettings';
import { Section } from '../components/Section';

interface Props {
  id: string;
}

const ModeOptions = {
  SETTINGS: 'SETTINGS',
  CHANGE_ICON: 'CHANGE_ICON'
} as const;

type Mode = keyof typeof ModeOptions;

/** Full-width host strip at the bottom of the header, such as the CMDB binding. */
const HEADER_STRIP_HEIGHT = 28;

export const NodeControls = ({ id }: Props) => {
  const [mode, setMode] = useState<Mode>('SETTINGS');
  const { updateModelItem, updateViewItem, deleteViewItem } = useScene();
  const uiStateActions = useUiStateStore((state) => {
    return state.actions;
  });
  const viewItem = useViewItem(id);
  const modelItem = useModelItem(id);
  const { iconCategories } = useIconCategories();
  const { icon } = useIcon(modelItem.icon);
  const labels = useLabels();
  const strip = useItemControlsExtra({ type: 'ITEM', id });

  const onSwitchMode = useCallback((newMode: Mode) => {
    setMode(newMode);
  }, []);

  return (
    <ControlsContainer>
      <Box
        sx={{
          bgcolor: (theme) => {
            return theme.customVars.customPalette.diagramBg;
          }
        }}
      >
        {/*
          With a host strip the icon row tightens (8 + 58 + 8) so the strip
          (28) keeps the header at its original 16 + 70 + 16 = 102px.
        */}
        <Section sx={{ py: strip ? 1 : 2 }}>
          <Stack
            direction="row"
            spacing={2}
            alignItems={strip ? 'center' : 'flex-end'}
            justifyContent="space-between"
          >
            <Box
              component="img"
              src={icon.url}
              sx={{ width: strip ? 58 : 70, height: strip ? 58 : 70 }}
            />
            {mode === 'SETTINGS' && (
              <Button
                endIcon={<ChevronRightIcon />}
                onClick={() => {
                  onSwitchMode('CHANGE_ICON');
                }}
                variant="text"
              >
                {labels.updateIcon}
              </Button>
            )}
            {mode === 'CHANGE_ICON' && (
              <Button
                startIcon={<ChevronLeftIcon />}
                onClick={() => {
                  onSwitchMode('SETTINGS');
                }}
                variant="text"
              >
                {labels.settings}
              </Button>
            )}
          </Stack>
        </Section>
        {strip ? (
          <Box
            data-testid="item-controls-strip"
            sx={{
              boxSizing: 'border-box',
              height: HEADER_STRIP_HEIGHT,
              px: 3,
              display: 'flex',
              alignItems: 'center',
              overflow: 'hidden',
              borderTop: '1px solid #e1eaf6',
              bgcolor: '#ebf2fb'
            }}
          >
            {strip}
          </Box>
        ) : null}
      </Box>
      {mode === 'SETTINGS' && (
        <NodeSettings
          key={viewItem.id}
          node={viewItem}
          onModelItemUpdated={(updates) => {
            updateModelItem(viewItem.id, updates);
          }}
          onViewItemUpdated={(updates) => {
            updateViewItem(viewItem.id, updates);
          }}
          onDeleted={() => {
            uiStateActions.setItemControls(null);
            deleteViewItem(viewItem.id);
          }}
        />
      )}
      {mode === 'CHANGE_ICON' && (
        <Icons
          key={viewItem.id}
          iconCategories={iconCategories}
          onClick={(_icon) => {
            updateModelItem(viewItem.id, { icon: _icon.id });
          }}
        />
      )}
    </ControlsContainer>
  );
};
