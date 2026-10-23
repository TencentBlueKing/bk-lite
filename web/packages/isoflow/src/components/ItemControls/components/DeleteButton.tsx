import React from 'react';
import { DeleteOutlined as DeleteIcon } from '@mui/icons-material';
import { Button } from '@mui/material';
import { useLabels } from 'src/hooks/useLabels';

interface Props {
  onClick: () => void;
}

export const DeleteButton = ({ onClick }: Props) => {
  const labels = useLabels();

  return (
    <Button
      color="error"
      size="small"
      variant="outlined"
      startIcon={<DeleteIcon sx={{ color: 'var(--color-fail)' }} />}
      onClick={onClick}
      sx={{
        alignSelf: 'flex-start',
        width: 'auto',
        minWidth: 0,
        height: 32,
        fontSize: 13,
        color: 'var(--color-fail)',
        fontWeight: 500,
        borderRadius: '6px',
        borderColor: 'var(--color-fail)',
        bgcolor: '#FFFFFF',
        '&:hover': {
          borderColor: 'var(--color-fail)',
          bgcolor: 'color-mix(in srgb, var(--color-fail) 8%, #FFFFFF)'
        }
      }}
    >
      {labels.delete}
    </Button>
  );
};
