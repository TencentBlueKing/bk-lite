export const isMonitorViewDemoEnabled = () =>
  process.env.NODE_ENV === 'development'
  && process.env.NEXT_PUBLIC_MONITOR_VIEW_MOCK !== 'false';
