import React from 'react';
import { Box } from '@mui/material';
import { Icon as IconI } from 'src/types';
import { Icon } from './Icon';

interface Props {
  icons: IconI[];
  onMouseDown?: (icon: IconI) => void;
  onClick?: (icon: IconI) => void;
}

export const IconGrid = ({ icons, onMouseDown, onClick }: Props) => {
  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', alignContent: 'flex-start' }}>
      {icons.map((icon) => {
        return (
          <Icon
            key={icon.id}
            icon={icon}
            onClick={() => {
              onClick?.(icon);
            }}
            onMouseDown={() => {
              onMouseDown?.(icon);
            }}
          />
        );
      })}
    </Box>
  );
};
