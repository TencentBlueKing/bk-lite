import React from 'react';
import { Box } from '@mui/material';

interface Props {
  header?: React.ReactNode;
  children: React.ReactNode;
}

export const ControlsContainer = ({ header, children }: Props) => {
  return (
    <Box
      sx={{
        position: 'relative',
        width: '100%',
        minHeight: 0,
        maxHeight: 'inherit',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden'
      }}
    >
      {header ? (
        <Box sx={{ width: '100%', flexShrink: 0 }}>{header}</Box>
      ) : null}
      <Box
        sx={{
          width: '100%',
          minHeight: 0,
          flex: '1 1 auto',
          overflowY: 'auto',
          pb: 2,
          scrollbarWidth: 'thin',
          scrollbarColor: 'var(--color-fill-4) transparent',
          '&::-webkit-scrollbar': {
            width: 6,
            height: 6,
            backgroundColor: 'transparent'
          },
          '&::-webkit-scrollbar-thumb': {
            borderRadius: 10,
            background: 'var(--color-fill-4)',
            opacity: 1
          }
        }}
      >
        {children}
      </Box>
    </Box>
  );
};
