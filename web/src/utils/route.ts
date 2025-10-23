// Extract client_id from current route (client-side only)
export const getClientIdFromRoute = (): string => {
  // Only works on client-side
  if (typeof window === 'undefined') {
    return 'ops-console'; // Default fallback for SSR
  }
  
  const pathname = window.location.pathname;
  const pathSegments = pathname.split('/').filter(Boolean);
  
  // If it's auth/signin route, return default client_id
  if (pathSegments.length > 0 && pathSegments[0] === 'auth') {
    return 'ops-console';
  }
  
  // Route format: /opspilot/xxx or /client-name/xxx - take the first segment as client_id
  if (pathSegments.length > 0) {
    return pathSegments[0];
  }
  
  return 'ops-console';
};

// Map route-based client_id to actual client name
export const mapClientName = (routeClientId: string): string => {
  const clientNameMap: { [key: string]: string } = {
    'node-manager': 'node',
    // Add more mappings here if needed
  };
  
  return clientNameMap[routeClientId] || routeClientId;
};