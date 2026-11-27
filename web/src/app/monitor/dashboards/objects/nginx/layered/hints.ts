export interface NginxHintCopy {
  lead: string;
  body: string;
}

export const NGINX_HINTS = {
  events: {
    lead: '事件',
    body: '当前时间范围内发生的告警触发与恢复。'
  },
  alerts: {
    lead: '告警数量',
    body: '当前仍未恢复的告警总数。'
  },
  request: {
    lead: '请求速率',
    body: '所选时间范围内，Nginx 平均每秒处理的 HTTP 请求数。'
  },
  active: {
    lead: '活跃连接',
    body: '此刻与客户端保持着的连接数，包括正在读、正在写和空闲等待的连接。'
  },
  requestJump: {
    lead: '请求是否骤变',
    body: '当前请求速率，与所选时间范围内平均水平相比的升降幅度。'
  },
  connectionLoss: {
    lead: '是否在丢连接',
    body: '丢弃连接速率：已接受、但未能进入处理就被关闭的连接，按每秒计。正常为 0。\n连接处理完成率：处理完成的连接 ÷ 接受的连接 × 100%。'
  },
  siteUpstream: {
    lead: '站点与上游异常',
    body: '5xx 次数：所选时间范围内的服务端错误响应次数。\n已下线成员：被标记为下线的上游服务器数量。'
  },
  connStructure: {
    lead: '连接结构',
    body: '正在读写的连接与空闲等待连接的数量对比。'
  },
  acceptHandled: {
    lead: '连接接受与处理速率',
    body: '每秒新接受的连接数，以及每秒处理完成的连接数。两条线重合说明连接都被正常处理。'
  },
  reading: {
    lead: '读取连接',
    body: '正在读取客户端请求头的连接数。'
  },
  writing: {
    lead: '写入连接',
    body: '正在向客户端返回响应的连接数，包括等待上游返回的连接。'
  },
  waiting: {
    lead: '等待连接',
    body: '保持着的空闲长连接数，等待客户端发起下一个请求。'
  },
  busy: {
    lead: '繁忙连接',
    body: '正在读取或写入的连接数，即读取连接加写入连接。'
  },
  droppedCount: {
    lead: '丢弃连接',
    body: '所选时间范围内，已接受、但未能进入处理就被关闭的连接次数。正常为 0。'
  },
  composition: {
    lead: '连接构成',
    body: '当前活跃连接中读取、写入、等待三类各有多少、各占多少。'
  },
  ratioTrend: {
    lead: '连接占比趋势',
    body: '繁忙连接占比：（读取连接 + 写入连接）÷ 活跃连接 × 100%。\n等待连接占比：等待连接 ÷ 活跃连接 × 100%。'
  },
  states: {
    lead: '连接数',
    body: '活跃、读取、写入、等待四类连接数随时间的变化，每分钟一个读数。'
  },
  dropped: {
    lead: '丢弃连接速率',
    body: '已接受、但未能进入处理就被关闭的连接，按每秒计。正常为 0。'
  },
  windowRequests: {
    lead: '窗口请求数',
    body: '所选时间范围内全部站点收到的请求总数。'
  },
  count4xx: {
    lead: '4xx 次数',
    body: '所选时间范围内的客户端错误响应次数，常见原因是地址错误或缺少权限。'
  },
  count5xx: {
    lead: '5xx 次数',
    body: '所选时间范围内的服务端错误响应次数。'
  },
  avgTime: {
    lead: '平均处理时间',
    body: 'Nginx 处理一个请求的平均耗时。'
  },
  statusDist: {
    lead: '状态码分布',
    body: '每个时间段内各类响应的次数。\n1xx：信息响应。2xx：成功。3xx：重定向。4xx：客户端错误。5xx：服务端错误。'
  },
  statusMix: {
    lead: '状态码构成',
    body: '所选时间范围内各类响应的次数与占比。'
  },
  bytes: {
    lead: '入站与出站流量',
    body: '入站：每秒从客户端收到的字节数。\n出站：每秒发给客户端的字节数。'
  },
  siteRate: {
    lead: '站点请求速率',
    body: '请求量最多的几个站点每秒的请求数，点击右侧排行可只看一个站点。'
  },
  siteRank: {
    lead: '站点请求排行',
    body: '所选时间范围内各站点的请求次数，从多到少排列。'
  },
  sites: {
    lead: '站点',
    body: '各站点在所选时间范围内的请求、响应类别、流量与平均处理时间。底部「全部站点」为整体合计。'
  },
  filter: {
    lead: '过滤器',
    body: '按过滤规则分组统计的请求、响应类别、流量与平均处理时间。'
  },
  upRate: {
    lead: '上游请求速率',
    body: 'Nginx 每秒转发给上游服务器的请求数。'
  },
  up5xx: {
    lead: '上游 5xx 次数',
    body: '所选时间范围内上游返回的服务端错误次数。'
  },
  upTime: {
    lead: '平均响应时间',
    body: '上游服务器返回响应的平均耗时，按各成员请求量加权。'
  },
  upOnline: {
    lead: '在线成员',
    body: '未被标记为下线的上游服务器数量，以及成员总数。'
  },
  upStatus: {
    lead: '上游状态码分布',
    body: '每个时间段内上游返回的各类响应次数。'
  },
  upStatusMix: {
    lead: '上游状态码构成',
    body: '所选时间范围内各类响应的次数与占比。'
  },
  upResponse: {
    lead: '响应时间',
    body: '各上游服务器返回响应的平均耗时。'
  },
  upRequestTime: {
    lead: '请求处理时间',
    body: '各上游服务器上请求从转发到完成的平均耗时。'
  },
  upstream: {
    lead: '上游',
    body: '按上游组列出各成员的状态、权重、请求、错误、流量和耗时。\n在线：正常接收请求。已下线：被配置为下线。备份：仅在其他成员不可用时接收请求。'
  }
} as const satisfies Record<string, NginxHintCopy>;
