import { ALGORITHMS_TYPE } from "@/app/mlops/constants";

const useParamsUtil = () => {
  // 超参数转换成表单数据
  const hyperoptConversion = (params: object) => {
    if (!params) return;
    const hyperopt_config: Record<string, any> = {};
    Object.entries(params).forEach(([key, value]) => {
      if (value?.type === 'randint') {
        hyperopt_config[key] = [value?.min, value?.max];
      } else if (value?.type === 'choice') {
        hyperopt_config[key] = value?.choice;
      }
    });
    return hyperopt_config;
  };

  // 表单数据转为请求参数
  const renderParams = (object: Record<string, any>, key: string) => {
    const hyperopt_config: Record<string, any> = {};
    if(!object) return hyperopt_config;
    Object.keys(object).forEach((item: string) => {
      if (ALGORITHMS_TYPE[key][item] == 'randint') {
        hyperopt_config[item] = {
          type: 'randint',
          min: object[item][0],
          max: object[item][1]
        }
      } else if (ALGORITHMS_TYPE[key][item] == 'choice') {
        hyperopt_config[item] = {
          type: 'choice',
          choice: object[item]
        }
      }
    });
    return hyperopt_config;
  };

  return {
    hyperoptConversion,
    renderParams
  }
};

export default useParamsUtil;