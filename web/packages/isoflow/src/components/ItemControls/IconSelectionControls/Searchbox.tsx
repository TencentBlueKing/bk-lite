import React from 'react';
import { TextField, InputAdornment } from '@mui/material';
import { Search as SearchIcon } from '@mui/icons-material';
import { useLabels } from 'src/hooks/useLabels';

interface Props {
  value: string;
  onChange: (value: string) => void;
}

export const Searchbox = ({ value, onChange }: Props) => {
  const labels = useLabels();

  return (
    <TextField
      fullWidth
      placeholder={labels.searchIcons}
      value={value}
      onChange={(e) => {
        return onChange(e.target.value as string);
      }}
      InputProps={{
        startAdornment: (
          <InputAdornment position="start">
            <SearchIcon />
          </InputAdornment>
        )
      }}
    />
  );
};
