import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';

const belongsToQueryObject = (option: InputOption, queryObject: string) => {
  if (!Array.isArray(option.query_objects) || option.query_objects.length === 0) return true;
  return option.query_objects.includes(queryObject);
};

/** 按查询对象收窄静态下拉。未选对象时保留全部选项，避免表单还没填就被清空。 */
export const narrowInputConfigForQueryObject = (
  inputConfig: InputControlConfig | undefined,
  queryObject: unknown,
): InputControlConfig | undefined => {
  if (
    !inputConfig
    || inputConfig.control === 'input'
    || inputConfig.control === 'organization'
    || inputConfig.control === 'conditionFilter'
    || inputConfig.control === 'order'
  ) {
    return inputConfig;
  }
  if (inputConfig.optionsSource.type !== 'static') return inputConfig;
  const selected = queryObject === undefined || queryObject === null ? '' : String(queryObject);
  if (!selected) return inputConfig;
  const items = inputConfig.optionsSource.staticItems;
  if (!items.some((item) => Array.isArray(item.query_objects) && item.query_objects.length > 0)) {
    return inputConfig;
  }
  return {
    ...inputConfig,
    optionsSource: {
      ...inputConfig.optionsSource,
      staticItems: items.filter((item) => belongsToQueryObject(item, selected)),
    },
  };
};
