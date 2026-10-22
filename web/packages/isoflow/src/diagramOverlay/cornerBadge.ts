import type { SxProps, Theme } from '@mui/material';

/** Round count badge on icon name plates. Colors come from ALERT_BADGE_TONE. */
export const CORNER_BADGE_SX: SxProps<Theme> = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  boxSizing: 'border-box',
  minWidth: 20,
  height: 20,
  px: '5px',
  borderRadius: '10px',
  border: '2px solid #fff',
  fontSize: 11,
  fontWeight: 700,
  lineHeight: 1,
  whiteSpace: 'nowrap',
  fontVariantNumeric: 'tabular-nums',
  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.2)'
};
