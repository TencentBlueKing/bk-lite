import React from 'react';
import { Box, IconButton } from '@mui/material';
import { Close as CloseIcon } from '@mui/icons-material';
import { useIconCategories } from 'src/hooks/useIconCategories';
import { useIcon } from 'src/hooks/useIcon';
import { useScene } from 'src/hooks/useScene';
import { useViewItem } from 'src/hooks/useViewItem';
import { useUiStateStore } from 'src/stores/uiStateStore';
import { useModelItem } from 'src/hooks/useModelItem';
import { useLabels } from 'src/hooks/useLabels';
import { useIconPicker, useItemControlsExtra } from 'src/diagramOverlay/context';
import { ControlsContainer } from '../components/ControlsContainer';
import { NodeSettings } from './NodeSettings/NodeSettings';

interface Props {
  id: string;
}

export const NodeControls = ({ id }: Props) => {
  const openIconPicker = useIconPicker();
  const { updateModelItem, updateViewItem, deleteViewItem } = useScene();
  const uiStateActions = useUiStateStore((state) => {
    return state.actions;
  });
  const viewItem = useViewItem(id);
  const modelItem = useModelItem(id);
  const { iconCategories } = useIconCategories();
  const { icon } = useIcon(modelItem.icon);
  const labels = useLabels();
  const extra = useItemControlsExtra({ type: 'ITEM', id });

  return (
    <ControlsContainer
      header={
        <Box
          sx={{
            position: 'relative',
            height: 36,
            bgcolor: 'var(--color-bg)'
          }}
        >
          <Box
            component="h2"
            sx={{
              position: 'absolute',
              top: 12,
              left: 12,
              display: 'flex',
              alignItems: 'center',
              height: 24,
              m: 0,
              pr: 4,
              fontSize: 13,
              fontWeight: 600,
              lineHeight: 1,
              color: 'var(--color-text-1)'
            }}
          >
            {labels.nodeSettings}
          </Box>
          <IconButton
            size="small"
            aria-label={labels.cancel}
            onClick={() => {
              uiStateActions.setItemControls(null);
            }}
            sx={{
              position: 'absolute',
              top: 12,
              right: 12,
              boxSizing: 'border-box',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 24,
              height: 24,
              minWidth: 24,
              p: 0,
              m: 0,
              color: 'var(--color-text-3)'
            }}
          >
            <CloseIcon sx={{ display: 'block', fontSize: 16 }} />
          </IconButton>
        </Box>
      }
    >
      <NodeSettings
        key={viewItem.id}
        node={viewItem}
        iconUrl={icon.url}
        onOpenIconPicker={() => {
          openIconPicker?.({
            title: labels.updateIcon,
            icons: iconCategories.flatMap((category) => {
              return category.icons.map((item) => {
                return { id: item.id, name: item.name, url: item.url };
              });
            }),
            onSelect: (iconId) => {
              updateModelItem(viewItem.id, { icon: iconId });
            }
          });
        }}
        extra={extra}
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
    </ControlsContainer>
  );
};
