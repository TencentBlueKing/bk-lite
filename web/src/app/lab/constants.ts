/**
 * Lab 模块常量配置
 * 集中管理资源默认值、验证规则、正则表达式等常量
 */

/**
 * 资源默认值
 */
export const RESOURCE_DEFAULTS = {
  /** CPU 核数默认值 */
  CPU: 2,
  /** 内存大小默认值 */
  MEMORY: '4Gi',
  /** GPU 数量默认值 */
  GPU: 0,
  /** 存储卷大小默认值 */
  VOLUME: '50Gi',
  /** 默认端口 */
  PORT: 8888,
} as const;

/**
 * 验证规则常量
 */
export const VALIDATION = {
  /** CPU 核数范围 */
  CPU_RANGE: {
    MIN: 1,
    MAX: 32,
  },
  /** GPU 数量范围 */
  GPU_RANGE: {
    MIN: 0,
    MAX: 8,
  },
  /** 端口号范围 */
  PORT_RANGE: {
    MIN: 1,
    MAX: 65535,
  },
  /** 名称最大长度 */
  NAME_MAX_LENGTH: 100,
  /** 描述最大长度 */
  DESCRIPTION_MAX_LENGTH: 500,
  /** 版本号最大长度 */
  VERSION_MAX_LENGTH: 50,
  /** 镜像地址最大长度 */
  IMAGE_URL_MAX_LENGTH: 200,
  /** 访问端点最大长度 */
  ENDPOINT_MAX_LENGTH: 200,
} as const;

/**
 * 正则表达式
 */
export const REGEX = {
  /** Kubernetes 资源格式（如: 4Gi, 512Mi, 1Ti） */
  K8S_RESOURCE: /^(\d+)([MmGgTt][Ii]?)$/,
  /** 端口号验证（1-65535） */
  PORT: /^([1-9]\d{0,3}|[1-5]\d{4}|6[0-4]\d{3}|65[0-4]\d{2}|655[0-2]\d|6553[0-5])$/,
} as const;

/**
 * 表单占位符提示
 */
export const PLACEHOLDERS = {
  /** CPU 输入占位符 */
  CPU: '2',
  /** 内存输入占位符 */
  MEMORY: '4Gi',
  /** GPU 输入占位符 */
  GPU: '0',
  /** 存储卷输入占位符 */
  VOLUME: '50Gi',
  /** 端口输入占位符 */
  PORT: '8888',
} as const;
