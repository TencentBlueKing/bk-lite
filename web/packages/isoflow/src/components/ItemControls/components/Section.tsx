import React from 'react';
import { Box, SxProps, Typography, Stack } from '@mui/material';

interface Props {
  children: React.ReactNode;
  title?: string;
  sx?: SxProps;
}

export const Section = ({ children, sx, title }: Props) => {
  return (
    <Box
      sx={{
        boxSizing: 'border-box',
        width: '100%',
        minWidth: 0,
        pt: 1.5,
        px: 1.5,
        ...sx
      }}
    >
      <Stack spacing={0.75} sx={{ width: '100%', minWidth: 0 }}>
        {title && (
          <Typography
            component="div"
            sx={{
              fontSize: 12,
              lineHeight: 1.4,
              fontWeight: 500,
              color: 'var(--color-text-3)',
              textTransform: 'none'
            }}
          >
            {title}
          </Typography>
        )}
        {children}
      </Stack>
    </Box>
  );
};
