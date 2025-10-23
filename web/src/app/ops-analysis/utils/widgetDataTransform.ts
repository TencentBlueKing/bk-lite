import dayjs from 'dayjs';

export const formatTimeRange = (timeParams: any): string[] => {
  let startTime, endTime;

  if (timeParams && typeof timeParams === 'number') {
    // 数值类型：表示分钟数
    endTime = dayjs().valueOf();
    startTime = dayjs().subtract(timeParams, 'minute').valueOf();
  } else if (timeParams && Array.isArray(timeParams) && timeParams.length === 2) {
    // 数组类型：[startTime, endTime]
    startTime = timeParams[0];
    endTime = timeParams[1];
  } else if (timeParams && timeParams.start && timeParams.end) {
    // 对象类型：{ start, end }
    startTime = timeParams.start;
    endTime = timeParams.end;
  } else {
    // 默认时间范围：最近7天
    endTime = dayjs().valueOf();
    startTime = dayjs().subtract(7, 'day').valueOf();
  }

  const startTimeStr = dayjs(startTime).format('YYYY-MM-DD HH:mm:ss');
  const endTimeStr = dayjs(endTime).format('YYYY-MM-DD HH:mm:ss');

  return [startTimeStr, endTimeStr];
};

export const fetchWidgetData = async ({
  config,
  globalTimeRange,
  getSourceDataByApiId,
}: {
  config: any;
  globalTimeRange?: any;
  getSourceDataByApiId: (dataSource: any, params: any) => Promise<any>;
}) => {
  if (!config?.dataSource) {
    return null;
  }

  try {
    const userParams: any = {};
    config.dataSourceParams?.forEach((param: any) => {
      userParams[param.name] = param.value;
    });

    const requestParams = processDataSourceParams({
      sourceParams: config.dataSourceParams,
      userParams,
      globalTimeRange
    });

    const rawData = await getSourceDataByApiId(config.dataSource, requestParams);
    return rawData;
  } catch (err: any) {
    console.error('获取数据失败:', err);
    return null;
  }
};

export const processDataSourceParams = ({
  sourceParams,
  userParams = {},
  globalTimeRange
}: {
  sourceParams: any;
  userParams?: Record<string, any>;
  globalTimeRange?: any;
}) => {

  if (!sourceParams || !Array.isArray(sourceParams)) {
    return userParams;
  }

  const processedParams = { ...userParams };

  sourceParams.forEach((param: any) => {
    const { name, filterType, value: defaultValue, type } = param;
    let finalValue;

    switch (filterType) {
      case 'fixed':
        finalValue = defaultValue;
        break;
      case 'filter':
        // filter 类型：时间范围使用全局时间，非时间范围使用默认值
        finalValue = (type === 'timeRange' && globalTimeRange) ? globalTimeRange : defaultValue;
        break;
      case 'params':
        finalValue = processedParams[name];
        break;
      default:
        finalValue = defaultValue;
    }

    processedParams[name] = (type === 'timeRange')
      ? formatTimeRange(finalValue)
      : finalValue;
  });

  return processedParams;
};
