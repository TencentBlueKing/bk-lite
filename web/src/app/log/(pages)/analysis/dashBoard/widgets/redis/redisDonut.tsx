import React, { useMemo } from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

// Redis 日志事件类型分布环形图
// 复用 DockerDonutChart，将聚合查询返回的多列数据转换为 [{name, count}] 格式
// 原始数据: rawData[0] = { total_count, err_count, type_err_count, auth_err_count, cmd_count }

const toNum = (v: unknown) => {
  const n = parseFloat(String(v ?? 0));
  return isNaN(n) ? 0 : n;
};

const RedisDonut: React.FC<any> = (props) => {
  const normalizedRawData = useMemo(() => {
    if (!Array.isArray(props.rawData) || props.rawData.length === 0) {
      return props.rawData;
    }
    const row = props.rawData[0] || {};
    const err = toNum(row.err_count);
    const typeErr = toNum(row.type_err_count);
    const authErr = toNum(row.auth_err_count);
    const cmd = toNum(row.cmd_count);
    const total = toNum(row.total_count);
    const other = Math.max(total - err - typeErr - authErr - cmd, 0);

    return [
      { name: 'ERR 错误', count: err },
      { name: '类型/集群错误', count: typeErr },
      { name: '认证失败', count: authErr },
      { name: '命令日志', count: cmd },
      { name: '其他', count: other }
    ].filter((item) => item.count > 0);
  }, [props.rawData]);

  const normalizedConfig = {
    ...props.config,
    displayMaps: {
      key: 'name',
      value: 'count'
    }
  };

  return (
    <DockerDonutChart
      {...props}
      rawData={normalizedRawData}
      config={normalizedConfig}
    />
  );
};

export default RedisDonut;
