export const MONITOR_NODE_PAGE_SIZE = 50;
export const MONITOR_NODE_SEARCH_DELAY_MS = 400;

export function scheduleMonitorNodeSearch(
  timer: { id?: number },
  delay: number,
  run: () => void,
) {
  if (timer.id) {
    window.clearTimeout(timer.id);
  }
  timer.id = window.setTimeout(run, delay);
}

export function shouldLoadNextMonitorNodePage(
  scrollTop: number,
  clientHeight: number,
  scrollHeight: number,
) {
  return scrollHeight - scrollTop - clientHeight <= 32;
}
