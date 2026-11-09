import {
  DOCKER_ERROR_LINE_SEARCH_QUERY,
  DOCKER_ERROR_LINE_STATS_QUERY,
  DOCKER_LOG_VS_ERROR_TREND_QUERY
} from '../dockerLogQueries';

describe('docker error line queries', () => {
  it('counts only log lines whose message contains ERROR or FATAL', () => {
    expect(DOCKER_ERROR_LINE_STATS_QUERY).toBe(
      'collect_type:"docker" | stats by (_time:${_time}) count() if (message:"ERROR" OR message:"FATAL") as errcount'
    );
    expect(DOCKER_ERROR_LINE_STATS_QUERY).not.toContain('extract');
    expect(DOCKER_ERROR_LINE_STATS_QUERY).not.toContain('count() as errcount');
  });

  it('opens the same ERROR or FATAL lines from the card', () => {
    expect(DOCKER_ERROR_LINE_SEARCH_QUERY).toBe(
      'collect_type:"docker" (message:"ERROR" OR message:"FATAL")'
    );
    expect(DOCKER_ERROR_LINE_SEARCH_QUERY).not.toContain('stream:');
  });

  it('plots error lines with the same condition as the error KPI', () => {
    expect(DOCKER_LOG_VS_ERROR_TREND_QUERY).toBe(
      'collect_type:"docker" | stats by (_time:${_time}) count() as logcount, count() if (message:"ERROR" OR message:"FATAL") as errcount'
    );
    expect(DOCKER_LOG_VS_ERROR_TREND_QUERY).not.toContain('stream:');
  });
});
