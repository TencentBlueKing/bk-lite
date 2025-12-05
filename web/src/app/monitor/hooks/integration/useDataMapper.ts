/**
 * 数据映射和转换处理器
 * 负责在 JSON 配置和 API 请求之间进行数据转换
 */
export class DataMapper {
  /**
   * 统一的数据转换处理
   * @param value - 原始值
   * @param dataTransform - 转换配置
   * @param direction - 转换方向：'toForm' 回显到表单，'toApi' 提交到API
   * @param apiData - 完整的API数据（用于获取源值）
   * @param formData - 完整的表单数据（用于 to_api 拼接）
   */
  static transformValue(
    value: any,
    dataTransform: any,
    direction: 'toForm' | 'toApi',
    apiData?: any,
    formData?: any
  ): any {
    if (!dataTransform) return value;
    // 如果是字符串，直接作为路径使用（兼容旧格式）
    if (typeof dataTransform === 'string') {
      return direction === 'toForm' && apiData
        ? this.getNestedValue(apiData, dataTransform)
        : value;
    }
    // 新格式 transform_on_edit：{ origin_path, to_form, to_api }
    const { origin_path, to_form, to_api } = dataTransform;
    let processedValue = value;
    // 回显到表单
    if (direction === 'toForm' && apiData) {
      // 1. 获取源数据
      const originValue = origin_path
        ? this.getNestedValue(apiData, origin_path)
        : value;
      processedValue = originValue;
      // 2. 应用 to_form 转换
      if (to_form) {
        // 正则提取
        if (to_form.regex && typeof processedValue === 'string') {
          const match = processedValue.match(new RegExp(to_form.regex));
          processedValue = match ? match[1] || match[0] : processedValue;
        }
        // 类型转换
        if (to_form.type) {
          switch (to_form.type) {
            case 'number':
              processedValue = Number(processedValue);
              break;
            case 'string':
              processedValue = String(processedValue);
              break;
            case 'parseInt':
              processedValue = parseInt(processedValue, 10);
              break;
            case 'parseFloat':
              processedValue = parseFloat(processedValue);
              break;
          }
        }
      }
    }
    // 提交到API
    if (direction === 'toApi') {
      // 如果没有 to_api 配置，表示不需要处理
      if (!to_api) {
        return undefined; // 返回 undefined 表示不写入
      }
      // 应用 to_api 转换
      if (to_api.type) {
        switch (to_api.type) {
          case 'number':
            processedValue = Number(processedValue);
            break;
          case 'string':
            processedValue = String(processedValue);
            break;
        }
      }
      // 添加前缀
      if (
        to_api.prefix &&
        processedValue !== undefined &&
        processedValue !== null
      ) {
        processedValue = to_api.prefix + String(processedValue);
      }
      // 添加后缀
      if (
        to_api.suffix &&
        processedValue !== undefined &&
        processedValue !== null
      ) {
        processedValue = String(processedValue) + to_api.suffix;
      }
      // 模板拼接（支持从 formData 获取其他字段）
      if (to_api.template && formData) {
        const templateResult = this.applyTemplate(
          to_api.template,
          formData,
          {}
        );
        // 如果目标是数组(如 agents),包装成数组
        processedValue = to_api.array ? [templateResult] : templateResult;
      }
    }
    return processedValue;
  }

  /**
   * Auto 模式：将表单和表格数据转换为 API 请求参数
   */
  static transformAutoRequest(
    formData: any,
    tableData: any[],
    context: {
      config_type: string | string[];
      collect_type: string;
      collector: string;
      instance_type: string;
      objectId?: string;
      nodeList?: any[];
      instance_id?: string;
      config_type_field?: string; // 从表单字段获取config_type的字段名(如主机的metric_type)
      formFields?: any[]; // 表单字段配置数组，用于处理 transform_on_create
    }
  ) {
    // 获取config_type数组
    let configTypes: string[];
    if (context.config_type_field && formData[context.config_type_field]) {
      // 从表单字段获取(如主机的metric_type)
      configTypes = Array.isArray(formData[context.config_type_field])
        ? formData[context.config_type_field]
        : [formData[context.config_type_field]];
      // 从formData中移除该字段
      delete formData[context.config_type_field];
    } else {
      // 使用配置中的config_type
      configTypes = Array.isArray(context.config_type)
        ? context.config_type
        : [context.config_type];
    }

    // 处理表单字段的 transform_on_create（auto 模式专用的字段转换配置）
    const processedFormData: any = {};
    const fieldsToDelete: string[] = []; // 记录已转换到嵌套路径的字段名，避免重复出现在顶层
    if (context.formFields) {
      context.formFields.forEach((field: any) => {
        const { name, transform_on_create } = field;
        const fieldValue = formData[name];
        if (fieldValue !== undefined && transform_on_create?.target_path) {
          // 如果字段有 transform_on_create.target_path 配置，设置到指定路径
          // 例如：username -> custom_headers.username
          this.setNestedValue(
            processedFormData,
            transform_on_create.target_path,
            fieldValue
          );
          // 标记该字段已处理，后续不再复制到顶层
          fieldsToDelete.push(name);
        } else if (fieldValue !== undefined) {
          // 普通字段直接复制到顶层
          processedFormData[name] = fieldValue;
        }
      });
      // 复制其他未在配置中的字段（排除已转换的字段）
      Object.keys(formData).forEach((key) => {
        if (!processedFormData[key] && !fieldsToDelete.includes(key)) {
          processedFormData[key] = formData[key];
        }
      });
    } else {
      // 没有 formFields 配置时，直接使用原始 formData
      Object.assign(processedFormData, formData);
    }
    // 构建configs数组：每个config_type生成一个config
    const configs = configTypes.map((type: string) => ({
      ...processedFormData,
      type, // config的type字段
    }));
    // 转换 instances 部分
    const instances = tableData.map((row) => {
      // 从 row.node_ids 获取选中的节点 ID 数组
      // row.node_ids 可能是：
      // - 单选: 字符串 'node-001'
      // - 多选: 数组 ['node-001', 'node-002']
      // - 空值: null/undefined
      let nodeIds: string[] = [];
      if (Array.isArray(row.node_ids)) {
        nodeIds = row.node_ids;
      } else if (row.node_ids) {
        // 单选模式，将字符串转为数组
        nodeIds = [row.node_ids];
      }
      // 生成 instance_id（如果有模板）,使用 SHA256 哈希编码
      let instance_id = row.instance_id;
      if (!instance_id && context.instance_id) {
        instance_id = this.applyTemplate(context.instance_id, row, context);
      }
      // 过滤掉 key 字段和所有 _error 字段
      const cleanedInstanceData = Object.keys(row)
        .filter(fieldKey => fieldKey !== 'key' && !fieldKey.endsWith('_error'))
        .reduce((acc, fieldKey) => {
          acc[fieldKey] = row[fieldKey];
          return acc;
        }, {} as any);
      
      return {
        ...cleanedInstanceData,
        instance_id,
        node_ids: nodeIds,
        instance_type: context.instance_type,
      };
    });

    return {
      collect_type: context.collect_type,
      collector: context.collector,
      configs,
      instances,
    };
  }

  /**
   * 使用 SHA256 哈希对 instance_id 进行编码
   * 生成固定长度的 base64 字符串（去除 '=' 填充符）
   * 注意：这是一个简化的哈希实现，确保每次输入相同的字符串生成相同的输出
   */
  private static hashInstanceId(instanceId: string): string {
    // 计算字符串哈希值
    let hash = 0;
    for (let i = 0; i < instanceId.length; i++) {
      const char = instanceId.charCodeAt(i);
      hash = (hash << 5) - hash + char;
      hash = hash & hash;
    }
    // 转为 8 位十六进制
    const hashHex = (hash >>> 0).toString(16).padStart(8, '0');
    // 确保 combined 足够长（至少 16 个字符，才能保证 base64 后有 10+ 位）
    // 如果原字符串不够长，用哈希值填充
    const padding = instanceId.padEnd(10, hashHex);
    const combined = hashHex + padding.slice(0, 10);
    // base64 编码
    const b64 = btoa(combined);
    // 去除 '=' 填充符，取前 10 位（如果不够 10 位，用 '0' 补齐）
    const result = b64.replace(/=/g, '');
    return result.padEnd(10, '0').slice(0, 10);
  }

  /**
   * 应用模板（替换 {{变量}}）
   * 支持三种变量来源：
   * 1. data 中的直接字段：{{ip}}, {{instance_name}}
   * 2. context 中的字段：{{objectId}}, {{instance_type}}
   * 3. 从 node_ids 对应的节点中提取：{{cloud_region}}, {{node_name}} 等
   */
  private static applyTemplate(
    template: string,
    data: any,
    context: any
  ): string {
    let result = template;
    // 1. 替换数据字段（当前行的字段）
    Object.entries(data).forEach(([key, value]) => {
      if (value !== null && value !== undefined) {
        result = result.replace(new RegExp(`{{${key}}}`, 'g'), String(value));
      }
    });
    // 2. 替换上下文字段
    Object.entries(context).forEach(([key, value]) => {
      if (value !== null && value !== undefined) {
        result = result.replace(new RegExp(`{{${key}}}`, 'g'), String(value));
      }
    });
    // 3. 从节点数据中提取字段（如果有 node_ids 和 nodeList）
    if (data.node_ids && context.nodeList) {
      // 获取第一个选中的节点ID
      const firstNodeId = Array.isArray(data.node_ids)
        ? data.node_ids[0]
        : data.node_ids;
      if (firstNodeId) {
        // 在 nodeList 中查找对应的节点
        const node = context.nodeList.find(
          (n: any) => n.value === firstNodeId || n.id === firstNodeId
        );
        if (node) {
          // 替换节点中的所有字段
          Object.entries(node).forEach(([key, value]) => {
            if (value !== null && value !== undefined) {
              result = result.replace(
                new RegExp(`{{${key}}}`, 'g'),
                String(value)
              );
            }
          });
        }
      }
    }
    return result;
  }

  /**
   * 获取嵌套对象的值（支持点号路径，如 "agents[0].url"）
   */
  static getNestedValue(obj: any, path: string): any {
    // 处理数组索引，如 agents[0]
    const parts = path.split('.');
    let value = obj;
    for (const part of parts) {
      if (!value) return undefined;
      // 处理数组索引
      const arrayMatch = part.match(/^(\w+)\[(\d+)\]$/);
      if (arrayMatch) {
        const [, key, index] = arrayMatch;
        value = value[key]?.[parseInt(index, 10)];
      } else {
        value = value[part];
      }
    }
    return value;
  }

  /**
   * 设置嵌套对象的值（支持点号路径，如 "child.content.config.timeout"）
   */
  static setNestedValue(obj: any, path: string, value: any): void {
    const parts = path.split('.');
    let current = obj;
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      // 处理数组索引
      const arrayMatch = part.match(/^(\w+)\[(\d+)\]$/);
      if (arrayMatch) {
        const [, key, index] = arrayMatch;
        if (!current[key]) current[key] = [];
        if (!current[key][parseInt(index, 10)]) {
          current[key][parseInt(index, 10)] = {};
        }
        current = current[key][parseInt(index, 10)];
      } else {
        if (!current[part]) current[part] = {};
        current = current[part];
      }
    }
    // 设置最后一个属性
    const lastPart = parts[parts.length - 1];
    const arrayMatch = lastPart.match(/^(\w+)\[(\d+)\]$/);
    if (arrayMatch) {
      const [, key, index] = arrayMatch;
      if (!current[key]) current[key] = [];
      current[key][parseInt(index, 10)] = value;
    } else {
      current[lastPart] = value;
    }
  }
}
