import { v4 as uuidv4 } from "uuid";
import {
  DataSourcePreviewResult,
  DataSourceSourceType,
  ParamItem,
  ResponseFieldDefinition,
} from "@/app/ops-analysis/types/dataSource";
import { validateDateRangeValue } from "@/app/ops-analysis/utils/dateRange";
import {
  isBindableDataSourceParamType,
} from "@/app/ops-analysis/utils/dataSourceParamContract";

export const SOURCE_TYPE_NATS: DataSourceSourceType = "nats";
export const SOURCE_TYPE_MYSQL: DataSourceSourceType = "mysql";
export const SOURCE_TYPE_POSTGRESQL: DataSourceSourceType = "postgresql";
export const SOURCE_TYPE_REST_API: DataSourceSourceType = "rest_api";
export const SOURCE_TYPE_EXCEL: DataSourceSourceType = "excel";
export const SOURCE_TYPE_PROMETHEUS: DataSourceSourceType = "prometheus";

export const PROMETHEUS_DEFAULT_CHART_TYPES = [
  "line",
  "bar",
  "single",
  "pie",
  "multiValue",
  "gauge",
  "table",
  "topN",
] as const;

export function createPrometheusDefaultParams(): ParamItem[] {
  return [
    {
      id: uuidv4(),
      name: "query",
      alias_name: "PromQL",
      type: "string",
      filterType: "params",
      value: "",
      required: true,
    },
    {
      id: uuidv4(),
      name: "query_type",
      alias_name: "查询类型",
      type: "string",
      filterType: "params",
      value: "range",
      inputConfig: {
        control: "select",
        optionsSource: {
          type: "static",
          staticItems: [
            { label: "range", value: "range" },
            { label: "instant", value: "instant" },
          ],
        },
      },
    },
    {
      id: uuidv4(),
      name: "time_range",
      alias_name: "时间范围",
      type: "timeRange",
      filterType: "filter",
      value: 60,
    },
    {
      id: uuidv4(),
      name: "step",
      alias_name: "Step",
      type: "string",
      filterType: "params",
      value: "1m",
    },
    {
      id: uuidv4(),
      name: "max_series",
      alias_name: "最大序列数",
      type: "number",
      filterType: "params",
      value: 20,
    },
  ];
}
export const TABLE_CHART_TYPE = "table";
export const PASSWORD_PLACEHOLDER = "******";

export function normalizePrometheusTimeRange(
  value: unknown,
): string[] | number | undefined {
  if (typeof value === "number" && value > 0) {
    const end = new Date();
    const start = new Date(end.getTime() - value * 60 * 1000);
    return [start.toISOString(), end.toISOString()];
  }
  if (Array.isArray(value) && value.length === 2) {
    return value.map(String) as string[];
  }
  return undefined;
}

export function prometheusTimeRangeToMinutes(value: unknown): number {
  if (typeof value === "number" && value > 0) {
    return value;
  }
  if (Array.isArray(value) && value.length === 2) {
    const start = new Date(String(value[0])).getTime();
    const end = new Date(String(value[1])).getTime();
    if (!Number.isNaN(start) && !Number.isNaN(end) && end > start) {
      return Math.max(1, Math.round((end - start) / 60000));
    }
  }
  return 60;
}

export type SchemaField = ResponseFieldDefinition & { id: string };

export const formatJsonText = (value: unknown) => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return "";
  }
  return JSON.stringify(value, null, 2);
};

export const parseJsonObject = (
  value: string | undefined,
  errorMessage: string,
) => {
  const text = (value || "").trim();
  if (!text) return {};
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
  } catch {
    // fall through to a unified validation error
  }
  throw new Error(errorMessage);
};

export const createDefaultParam = (): ParamItem => ({
  id: uuidv4(),
  name: "",
  value: "",
  type: "string",
  filterType: "fixed",
  alias_name: "",
});

export const createDefaultSchemaField = (): SchemaField => ({
  id: uuidv4(),
  key: "",
  title: "",
  value_type: "string",
  description: "",
});

export const validateParams = (currentParams: ParamItem[]) => {
  const nameCount: { [key: string]: number } = {};
  const duplicateNames: string[] = [];
  const emptyNames: string[] = [];
  const emptyAliases: string[] = [];
  const invalidDateRangeIds: string[] = [];
  const invalidFilterBindingIds: string[] = [];
  let hasInvalidDateRange = false;

  currentParams.forEach((param) => {
    if (param.name && param.name.trim()) {
      nameCount[param.name] = (nameCount[param.name] || 0) + 1;
    } else if (param.id) {
      emptyNames.push(param.id);
    }

    if ((!param.alias_name || !param.alias_name.trim()) && param.id) {
      emptyAliases.push(param.id);
    }

    if (param.type === "dateRange" && !validateDateRangeValue(param.value).valid) {
      hasInvalidDateRange = true;
      if (param.id) invalidDateRangeIds.push(param.id);
    }

    if (
      param.filterType === "filter" &&
      !isBindableDataSourceParamType(param.type) &&
      param.id
    ) {
      invalidFilterBindingIds.push(param.id);
    }
  });

  Object.keys(nameCount).forEach((name) => {
    if (nameCount[name] > 1) {
      duplicateNames.push(name);
    }
  });

  const validParams = currentParams.filter(
    (param) => param.name && param.name.trim(),
  );
  const hasEmptyFixedValue = validParams.some((param) => {
    if (param.filterType !== "fixed" || param.type === "dateRange") return false;
    const value = param.value;
    return value === "" || value === null || value === undefined;
  });

  return {
    duplicateNames,
    emptyNames,
    emptyAliases,
    invalidDateRangeIds,
    invalidFilterBindingIds,
    hasEmptyFixedValue,
    isValid:
      duplicateNames.length === 0 &&
      emptyNames.length === 0 &&
      emptyAliases.length === 0 &&
      !hasInvalidDateRange &&
      invalidFilterBindingIds.length === 0 &&
      !hasEmptyFixedValue,
  };
};

export const validateSchemaFields = (fields: SchemaField[]) => {
  const keyCount: { [key: string]: number } = {};
  const duplicateFieldKeys: string[] = [];
  const emptyFieldKeys = fields
    .filter((field) => !field.key || !field.key.trim())
    .map((field) => field.id);

  fields.forEach((field) => {
    if (field.key && field.key.trim()) {
      keyCount[field.key] = (keyCount[field.key] || 0) + 1;
    }
  });

  Object.keys(keyCount).forEach((key) => {
    if (keyCount[key] > 1) {
      duplicateFieldKeys.push(key);
    }
  });

  return {
    duplicateFieldKeys,
    emptyFieldKeys,
    isValid: duplicateFieldKeys.length === 0 && emptyFieldKeys.length === 0,
  };
};

export const normalizeFieldSchema = (schemaFields: SchemaField[]) =>
  schemaFields.map(({ key, title, value_type, description }) => ({
    key: key.trim(),
    title: title.trim(),
    value_type,
    description: description?.trim() || "",
  }));

export const normalizeParams = (params: ParamItem[]) =>
  params
    .filter((param) => param.name && param.name.trim())
    .map((param) => ({
      name: param.name,
      alias_name: param.alias_name,
      type: param.type,
      filterType: param.filterType,
      value: param.value,
      required: param.required,
    }));

export const buildConnectorPayload = (
  values: any,
  options: {
    excelFileName?: string;
    previewData?: DataSourcePreviewResult | null;
    t: (key: string) => string;
  },
) => {
  const currentSourceType =
    (values.source_type as DataSourceSourceType) || SOURCE_TYPE_NATS;
  const connectionConfig = values.connection_config || {};
  const queryConfig = values.query_config || {};

  if (currentSourceType === SOURCE_TYPE_REST_API) {
    return {
      source_type: currentSourceType,
      connection_config: {
        url: connectionConfig.url,
        method: connectionConfig.method || "GET",
        timeout: connectionConfig.timeout || 10,
        headers: parseJsonObject(
          connectionConfig.headersText,
          `${options.t("dataSource.headers")}${options.t("dataSource.jsonObjectRequired")}`,
        ),
      },
      query_config: {
        response_path: queryConfig.response_path || "",
        params: parseJsonObject(
          queryConfig.paramsText,
          `${options.t("dataSource.queryParams")}${options.t("dataSource.jsonObjectRequired")}`,
        ),
        body: parseJsonObject(
          queryConfig.bodyText,
          `${options.t("dataSource.requestBody")}${options.t("dataSource.jsonObjectRequired")}`,
        ),
      },
    };
  }

  if (
    currentSourceType === SOURCE_TYPE_MYSQL ||
    currentSourceType === SOURCE_TYPE_POSTGRESQL
  ) {
    return {
      source_type: currentSourceType,
      connection_config: {
        host: connectionConfig.host,
        port: connectionConfig.port,
        database: connectionConfig.database,
        username: connectionConfig.username,
        password: connectionConfig.password,
      },
      query_config: {
        table: queryConfig.table || "",
        sql: queryConfig.sql || "",
      },
    };
  }

  if (currentSourceType === SOURCE_TYPE_EXCEL) {
    return {
      source_type: currentSourceType,
      connection_config: {
        filename: options.excelFileName || connectionConfig.filename || "",
      },
      query_config: {
        imported_items:
          options.previewData?.items || queryConfig.imported_items || [],
        imported_fields:
          options.previewData?.fields || queryConfig.imported_fields || [],
        imported_count:
          options.previewData?.count ||
          queryConfig.imported_count ||
          options.previewData?.items?.length ||
          0,
      },
    };
  }

  if (currentSourceType === SOURCE_TYPE_PROMETHEUS) {
    const authType = connectionConfig.auth_type || "none";
    const prometheusConnectionConfig: Record<string, unknown> = {
      url: connectionConfig.url,
      auth_type: authType,
    };
    if (
      connectionConfig.timeout_seconds !== undefined &&
      connectionConfig.timeout_seconds !== null &&
      connectionConfig.timeout_seconds !== ""
    ) {
      prometheusConnectionConfig.timeout_seconds =
        connectionConfig.timeout_seconds;
    }
    if (authType === "basic") {
      prometheusConnectionConfig.username = connectionConfig.username;
      prometheusConnectionConfig.password = connectionConfig.password;
    }
    if (authType === "bearer") {
      prometheusConnectionConfig.token = connectionConfig.token;
    }
    const queryType = queryConfig.query_type || "range";
    const normalizedQueryConfig: Record<string, unknown> = {
      query: queryConfig.query || "",
      query_type: queryType,
      step: queryConfig.step || "1m",
      max_series: queryConfig.max_series ?? 20,
    };
    if (queryType === "range") {
      const timeRange = normalizePrometheusTimeRange(queryConfig.time_range);
      if (timeRange) {
        normalizedQueryConfig.time_range = timeRange;
      }
    }
    return {
      source_type: currentSourceType,
      connection_config: prometheusConnectionConfig,
      query_config: normalizedQueryConfig,
    };
  }

  return {
    source_type: currentSourceType,
    connection_config: {},
    query_config: {},
  };
};
