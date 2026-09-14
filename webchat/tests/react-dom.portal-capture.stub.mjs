import React from 'react';

export function createPortal(children, container) {
  if (!globalThis.__webchatPortalTargets) {
    globalThis.__webchatPortalTargets = [];
  }
  globalThis.__webchatPortalTargets.push(container);
  return React.createElement(
    'div',
    {
      'data-testid': 'webchat-portal',
      'data-portal-target-id': container?.id ?? '',
    },
    children
  );
}
