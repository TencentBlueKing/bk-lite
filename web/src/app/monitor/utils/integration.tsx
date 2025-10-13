import { TableDataItem } from '@/app/monitor/types/monitor';

export const replaceTemplate = (
  template: string,
  data: { [key: string]: string | number }
): string => {
  return Object.keys(data).reduce((acc, key) => {
    // 使用正则表达式来匹配模板字符串中的 ${key} 或 $key
    const regex = new RegExp(`\\$${key}`, 'g');
    // 替换匹配到的内容为对象中的值
    return acc.replace(regex, (data[key] || 'null').toString());
  }, template);
};

export const extractMongoDBUrl = (url: string) => {
  const regex = /\/\/(?:(.+):(.+)@)?([^:]+):(\d+)/;
  const matches = url.match(regex);
  if (matches) {
    const [, username, password, host, port] = matches;
    const result: any = {};
    if (host) {
      result.host = host;
    }
    if (port) {
      result.port = port;
    }
    if (username && password) {
      result.username = username;
      result.password = password;
    }
    return result;
  }
  return {};
};

export const replaceMinioUrls = (
  urls: string[],
  { host, port }: { host: string; port: string }
) => {
  const regex = /^(https?:\/\/)[^\/:]+(?::\d+)?(\/minio\/.*)$/;
  return urls.map((url) => {
    return url.replace(regex, `$1${host}:${port}$2`);
  });
};

export const extractMysqlUrl = (url: string) => {
  const regex = /^([^:]+):([^@]+)@tcp\(([^:]+):(\d+)\)/;
  const matches = url.match(regex);
  if (!matches || matches.length < 5) {
    return {};
  }
  return {
    username: matches[1],
    password: matches[2],
    host: matches[3],
    port: matches[4],
  };
};

export const extractMssqlUrl = (url: string) => {
  const regex = /Server=([^;]+);Port=([^;]+);User Id=([^;]+);Password=([^;]+)/;
  const matches = url.match(regex);
  if (!matches || matches.length < 5) {
    return {};
  }
  return {
    username: matches[1],
    password: matches[2],
    host: matches[3],
    port: matches[4],
  };
};

export const extractPostgresUrl = (url: string) => {
  const result = {
    host: '',
    port: '',
    username: '',
    password: '',
  };
  const regex =
    /(?:host=([^\s]+))|(?:port=([^\s]+))|(?:user=([^\s]+))|(?:password=([^\s]+))/g;
  let match;
  while ((match = regex.exec(url)) !== null) {
    if (match[1]) result.host = match[1];
    if (match[2]) result.port = match[2];
    if (match[3]) result.username = match[3];
    if (match[4]) result.password = match[4];
  }
  return result;
};

export const extractBkpullUrl = (url: string) => {
  const regex = /^https?:\/\/([^:\/]+):(\d+)/;
  const matches = url.match(regex);
  if (!matches || matches.length < 3) {
    return {};
  }
  return {
    host: matches[1],
    port: matches[2],
  };
};

export const extractVmvareUrl = (obj: any) => {
  try {
    return {
      ...obj.http_headers,
      host: obj.tags.instance_id.replace('vc-', ''),
    };
  } catch {
    return {};
  }
};

export const extractIPMIUrl = (url: string) => {
  const regex = /([^:]+):([^@]+)@([^()]+)\(([^)]+)\)/;
  const match = url.match(regex);
  if (!match || match.length < 5) {
    return {};
  }
  return {
    monitor_ip: match[4],
    protocol: match[3],
    username: match[1],
    password: match[2],
  };
};

export const insertCredentialsToMongoDB = (
  config: string,
  params: TableDataItem
): string => {
  // 正则匹配 "mongodb://" 后的部分，直到 "$host:$port"
  const regex = /(mongodb:\/\/)(\$host:\$port)/;
  // 使用正则替换，将 username 和 password 插入到匹配的部分中
  const updatedConfig = config.replace(
    regex,
    `$1${params.username}:${params.password}@$2`
  );
  return updatedConfig;
};
