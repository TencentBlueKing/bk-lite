import React, { useCallback } from 'react';
import { useUiStateStore } from 'src/stores/uiStateStore';
import { getTilePosition, CoordsUtils } from 'src/utils';
import { useScene } from 'src/hooks/useScene';
import { useLabels } from 'src/hooks/useLabels';
import { ContextMenu } from './ContextMenu';

interface Props {
  anchorEl?: HTMLElement;
}

export const ContextMenuManager = ({ anchorEl }: Props) => {
  const scene = useScene();
  const labels = useLabels();
  const zoom = useUiStateStore((state) => {
    return state.zoom;
  });
  const contextMenu = useUiStateStore((state) => {
    return state.contextMenu;
  });

  const uiStateActions = useUiStateStore((state) => {
    return state.actions;
  });

  const onClose = useCallback(() => {
    uiStateActions.setContextMenu(null);
  }, [uiStateActions]);

  if (!contextMenu) {
    return null;
  }

  return (
    <ContextMenu
      anchorEl={anchorEl}
      onClose={onClose}
      position={CoordsUtils.multiply(
        getTilePosition({ tile: contextMenu.tile }),
        zoom
      )}
      menuItems={[
        {
          label: labels.sendBackward,
          onClick: () => {
            scene.changeLayerOrder('SEND_BACKWARD', contextMenu.item);
            onClose();
          }
        },
        {
          label: labels.bringForward,
          onClick: () => {
            scene.changeLayerOrder('BRING_FORWARD', contextMenu.item);
            onClose();
          }
        },
        {
          label: labels.sendToBack,
          onClick: () => {
            scene.changeLayerOrder('SEND_TO_BACK', contextMenu.item);
            onClose();
          }
        },
        {
          label: labels.bringToFront,
          onClick: () => {
            scene.changeLayerOrder('BRING_TO_FRONT', contextMenu.item);
            onClose();
          }
        }
      ]}
    />
  );
};
