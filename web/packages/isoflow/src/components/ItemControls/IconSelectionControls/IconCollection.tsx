import React from 'react';
import { Icon as IconI } from 'src/types';
import { IconGrid } from './IconGrid';

interface Props {
  icons: IconI[];
  onClick?: (icon: IconI) => void;
  onMouseDown?: (icon: IconI) => void;
}

export const IconCollection = ({ icons, onClick, onMouseDown }: Props) => {
  return <IconGrid icons={icons} onMouseDown={onMouseDown} onClick={onClick} />;
};
