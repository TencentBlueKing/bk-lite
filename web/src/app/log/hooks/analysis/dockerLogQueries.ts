const DOCKER_COLLECT_FILTER = 'collect_type:"docker"';

/**
 * 错误日志行：正文中出现单词 ERROR 或 FATAL。
 * 必须用 count() if，不能先 extract 再无条件 count()。
 * extract 只追加字段，不会丢掉未匹配的行。
 */
export const DOCKER_ERROR_LINE_CONDITION =
  'message:"ERROR" OR message:"FATAL"';

export const DOCKER_ERROR_LINE_SEARCH_QUERY = `${DOCKER_COLLECT_FILTER} (${DOCKER_ERROR_LINE_CONDITION})`;

export const DOCKER_ERROR_LINE_STATS_QUERY = `${DOCKER_COLLECT_FILTER} | stats by (_time:\${_time}) count() if (${DOCKER_ERROR_LINE_CONDITION}) as errcount`;

export const DOCKER_LOG_VS_ERROR_TREND_QUERY = `${DOCKER_COLLECT_FILTER} | stats by (_time:\${_time}) count() as logcount, count() if (${DOCKER_ERROR_LINE_CONDITION}) as errcount`;
