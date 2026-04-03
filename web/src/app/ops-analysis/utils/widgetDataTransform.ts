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
  dataSource,
  globalTimeRange,
  extraParams,
  getSourceDataByApiId,
}: {
  config: any;
    dataSource?: any;
  globalTimeRange?: any;
    extraParams?: Record<string, any>;
  getSourceDataByApiId: (dataSource: any, params: any) => Promise<any>;
}) => {
  if (!config?.dataSource) {
    return null;
  }

  try {
    const sourceParams =
      (Array.isArray(config?.dataSourceParams) && config.dataSourceParams.length > 0
        ? config.dataSourceParams
        : dataSource?.params) || [];

    const userParams: any = {};
    sourceParams.forEach((param: any) => {
      userParams[param.name] = param.value;
    });

    const requestParams = processDataSourceParams({
      sourceParams,
      userParams,
      globalTimeRange
    });

    const finalRequestParams = {
      ...requestParams,
      ...(extraParams || {}),
    };

    const rawData = await getSourceDataByApiId(config.dataSource, finalRequestParams);
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
