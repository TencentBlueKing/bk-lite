export const normalizeDashboardKey = (value?: string | null) => String(value || '').trim().toLowerCase();

export const isProfessionalDashboardRoute = (pathname?: string | null) => String(pathname || '').startsWith('/monitor/view/dashboard/');
