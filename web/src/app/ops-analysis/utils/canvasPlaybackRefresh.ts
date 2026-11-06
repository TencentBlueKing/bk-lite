/** 播放态强制关掉周期刷新。查看、编辑、分享仍由调用方原来的条件决定。 */
export const canvasPeriodicRefreshEnabled = (
  baseEnabled: boolean,
  playbackMode: boolean,
): boolean => baseEnabled && !playbackMode;
