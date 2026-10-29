import React from 'react';
import Box from '@mui/material/Box';
import { Button, Typography } from '@mui/material';
import { Icon as IconI } from 'src/types';

interface Props {
  icon: IconI;
  onClick?: () => void;
  onMouseDown?: () => void;
}

export const Icon = ({ icon, onClick, onMouseDown }: Props) => {
  return (
    <Button
      variant="text"
      onClick={onClick}
      onMouseDown={onMouseDown}
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '4px',
        boxSizing: 'border-box',
        flex: '0 0 25%',
        width: '25%',
        height: 70,
        minWidth: 0,
        p: '2px',
        borderRadius: 0,
        border: '1px dashed transparent',
        color: 'var(--color-text-2)',
        textTransform: 'none',
        userSelect: 'none',
        '&:hover': {
          borderColor: 'var(--color-primary)',
          bgcolor: 'transparent'
        }
      }}
    >
      <Box
        component="img"
        draggable={false}
        src={icon.url}
        alt={icon.name}
        sx={{ display: 'block', width: 38, height: 38 }}
      />
      <Typography
        component="span"
        sx={{
          maxWidth: '100%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          fontSize: 10,
          lineHeight: '12px',
          textAlign: 'center',
          color: 'var(--color-text-2)'
        }}
      >
        {icon.name}
      </Typography>
    </Button>
  );
};
