import React, { useCallback, useState } from 'react';
import { Button, Stack } from '@mui/material';
import {
  PanToolOutlined as PanToolIcon,
  NearMeOutlined as NearMeIcon,
  AddOutlined as AddIcon,
  EastOutlined as ConnectorIcon,
  CropSquareOutlined as CropSquareIcon,
  Title as TitleIcon,
  KeyboardDoubleArrowLeft as CollapseIcon,
  KeyboardDoubleArrowRight as ExpandIcon
} from '@mui/icons-material';
import { useUiStateStore } from 'src/stores/uiStateStore';
import { UiElement } from 'src/components/UiElement/UiElement';
import { useScene } from 'src/hooks/useScene';
import { TEXTBOX_DEFAULTS } from 'src/config';
import { generateId } from 'src/utils';
import { useLabels } from 'src/hooks/useLabels';

interface ToolItem {
  name: string;
  icon: React.ReactNode;
  isActive: boolean;
  onClick: () => void;
}

const TOOL_BUTTON_WIDTH = 36;

const toolButtonSx = (isActive: boolean) => {
  return {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '2px',
    minWidth: `${TOOL_BUTTON_WIDTH}px !important`,
    width: TOOL_BUTTON_WIDTH,
    maxWidth: TOOL_BUTTON_WIDTH,
    height: 'auto',
    minHeight: 40,
    padding: '4px 0',
    borderRadius: '6px',
    lineHeight: 1.15,
    color: isActive ? 'var(--color-primary)' : 'var(--color-text-2)',
    bgcolor: isActive ? 'var(--color-primary-bg)' : 'transparent',
    transition: 'background-color 120ms ease, color 120ms ease',
    '&:hover': {
      bgcolor: isActive ? 'var(--color-primary-bg)' : 'var(--color-fill-2)'
    },
    '& .MuiSvgIcon-root': {
      width: 16,
      height: 16,
      color: 'inherit'
    }
  };
};

export const ToolMenu = () => {
  const [collapsed, setCollapsed] = useState(false);
  const { createTextBox } = useScene();
  const labels = useLabels();
  const mode = useUiStateStore((state) => {
    return state.mode;
  });
  const uiStateStoreActions = useUiStateStore((state) => {
    return state.actions;
  });
  const mousePosition = useUiStateStore((state) => {
    return state.mouse.position.tile;
  });

  const createTextBoxProxy = useCallback(() => {
    const textBoxId = generateId();

    createTextBox({
      ...TEXTBOX_DEFAULTS,
      content: labels.newText,
      id: textBoxId,
      tile: mousePosition
    });

    uiStateStoreActions.setMode({
      type: 'TEXTBOX',
      showCursor: false,
      id: textBoxId
    });
  }, [uiStateStoreActions, createTextBox, mousePosition, labels.newText]);

  const tools: ToolItem[] = [
    {
      name: labels.toolSelect,
      icon: <NearMeIcon />,
      isActive: mode.type === 'CURSOR' || mode.type === 'DRAG_ITEMS',
      onClick: () => {
        uiStateStoreActions.setMode({
          type: 'CURSOR',
          showCursor: true,
          mousedownItem: null
        });
      }
    },
    {
      name: labels.toolPan,
      icon: <PanToolIcon />,
      isActive: mode.type === 'PAN',
      onClick: () => {
        uiStateStoreActions.setMode({
          type: 'PAN',
          showCursor: false
        });
        uiStateStoreActions.setItemControls(null);
      }
    },
    {
      name: labels.toolAddItem,
      icon: <AddIcon />,
      isActive: mode.type === 'PLACE_ICON',
      onClick: () => {
        uiStateStoreActions.setItemControls({
          type: 'ADD_ITEM'
        });
        uiStateStoreActions.setMode({
          type: 'PLACE_ICON',
          showCursor: true,
          id: null
        });
      }
    },
    {
      name: labels.toolConnector,
      icon: <ConnectorIcon />,
      isActive: mode.type === 'CONNECTOR',
      onClick: () => {
        uiStateStoreActions.setMode({
          type: 'CONNECTOR',
          id: null,
          showCursor: true
        });
      }
    },
    {
      name: labels.toolRectangle,
      icon: <CropSquareIcon />,
      isActive: mode.type === 'RECTANGLE.DRAW',
      onClick: () => {
        uiStateStoreActions.setMode({
          type: 'RECTANGLE.DRAW',
          showCursor: true,
          id: null
        });
      }
    },
    {
      name: labels.toolText,
      icon: <TitleIcon />,
      isActive: mode.type === 'TEXTBOX',
      onClick: createTextBoxProxy
    }
  ];

  return (
    <UiElement>
      <Stack direction="column" spacing={0.25} sx={{ p: '4px', width: TOOL_BUTTON_WIDTH + 8 }}>
        {tools.map((tool) => {
          return (
            <Button
              key={tool.name}
              variant="text"
              aria-pressed={tool.isActive}
              onClick={tool.onClick}
              sx={toolButtonSx(tool.isActive)}
            >
              {tool.icon}
              {collapsed ? null : (
                <span
                  style={{
                    fontSize: 10,
                    lineHeight: 1.15,
                    width: '100%',
                    whiteSpace: 'normal',
                    textAlign: 'center'
                  }}
                >
                  {tool.name}
                </span>
              )}
            </Button>
          );
        })}
        <Button
          variant="text"
          aria-label={collapsed ? labels.toolExpand : labels.toolCollapse}
          aria-expanded={!collapsed}
          onClick={() => {
            setCollapsed((current) => {
              return !current;
            });
          }}
          sx={{
            ...toolButtonSx(false),
            minHeight: 28,
            height: 28,
            mt: 0.25,
            borderTop: '1px solid var(--color-border-1)',
            borderRadius: 0
          }}
        >
          {collapsed ? <ExpandIcon /> : <CollapseIcon />}
        </Button>
      </Stack>
    </UiElement>
  );
};
