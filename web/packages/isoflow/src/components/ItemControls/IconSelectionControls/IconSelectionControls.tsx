import React, { useCallback } from 'react';
import { Stack, Alert } from '@mui/material';
import { ControlsContainer } from 'src/components/ItemControls/components/ControlsContainer';
import { useUiStateStore } from 'src/stores/uiStateStore';
import { Icon } from 'src/types';
import { Section } from 'src/components/ItemControls/components/Section';
import { Searchbox } from 'src/components/ItemControls/IconSelectionControls/Searchbox';
import { useIconFiltering } from 'src/hooks/useIconFiltering';
import { useIconCategories } from 'src/hooks/useIconCategories';
import { useLabels } from 'src/hooks/useLabels';
import { Icons } from './Icons';
import { IconGrid } from './IconGrid';

export const IconSelectionControls = () => {
  const uiStateActions = useUiStateStore((state) => {
    return state.actions;
  });
  const mode = useUiStateStore((state) => {
    return state.mode;
  });
  const { setFilter, filteredIcons, filter } = useIconFiltering();
  const { iconCategories } = useIconCategories();
  const labels = useLabels();

  const onMouseDown = useCallback(
    (icon: Icon) => {
      if (mode.type !== 'PLACE_ICON') return;

      uiStateActions.setMode({
        type: 'PLACE_ICON',
        showCursor: true,
        id: icon.id
      });
    },
    [mode, uiStateActions]
  );

  return (
    <ControlsContainer
      header={
        <Section sx={{ position: 'sticky', top: 0, pt: 1.5, pb: 1 }}>
          <Stack spacing={2}>
            <Searchbox value={filter} onChange={setFilter} />
            <Alert
              severity="info"
              sx={{
                alignItems: 'center',
                py: 0,
                px: 1.25,
                '& .MuiAlert-icon': {
                  fontSize: 16,
                  py: '4px',
                  mr: 0.75
                },
                '& .MuiAlert-message': {
                  py: '4px',
                  fontSize: 12,
                  lineHeight: '18px'
                }
              }}
            >
              {labels.dragHint}
            </Alert>
          </Stack>
        </Section>
      }
    >
      {filteredIcons && (
        <Section>
          <IconGrid icons={filteredIcons} onMouseDown={onMouseDown} />
        </Section>
      )}
      {!filteredIcons && (
        <Icons iconCategories={iconCategories} onMouseDown={onMouseDown} />
      )}
    </ControlsContainer>
  );
};
