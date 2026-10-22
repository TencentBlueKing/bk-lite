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
      startIcon={<DeleteIcon color="error" />}
      onClick={onClick}
    >
      {labels.delete}
    </Button>
  );
};
