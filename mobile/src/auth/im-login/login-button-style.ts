export const LOGIN_ACTION_BUTTON_CLASS = 'w-full h-11 rounded-lg shadow-sm';

export function loginActionButtonStyle(disabled: boolean) {
  const backgroundColor = disabled ? '#e5e7eb' : '#2563eb';
  return {
    backgroundColor,
    color: '#ffffff',
    borderRadius: '0.5rem',
    fontSize: '16px',
    fontWeight: '500',
    '--background-color': backgroundColor,
    '--border-color': backgroundColor,
    '--text-color': '#ffffff',
    '--border-radius': '0.5rem',
  };
}
