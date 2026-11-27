import { HOST_SERIES_COLOR } from '../../host/config';

/**
 * Nginx 专业盘折线色，跟主机序列色同一套。
 * 状态码五色不走这里，仍按分布语义色。
 */
export const NGINX_LINE = {
  request: HOST_SERIES_COLOR.cpu,
  active: HOST_SERIES_COLOR.memUsed,
  reading: HOST_SERIES_COLOR.cpu,
  writing: HOST_SERIES_COLOR.load1,
  waiting: HOST_SERIES_COLOR.diskUsed,
  accept: HOST_SERIES_COLOR.netIn,
  handled: HOST_SERIES_COLOR.memUsed,
  dropped: HOST_SERIES_COLOR.diskWrite,
  busy: HOST_SERIES_COLOR.load1,
  inbound: HOST_SERIES_COLOR.netIn,
  outbound: HOST_SERIES_COLOR.netOut,
  time: HOST_SERIES_COLOR.load5
} as const;
