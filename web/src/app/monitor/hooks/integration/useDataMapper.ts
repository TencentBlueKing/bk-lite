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
      let resolvedPath = origin_path;
      // 如果 origin_path 包含变量（如 {{config_id}}），先替换变量
      if (origin_path && origin_path.includes('{{')) {
        resolvedPath = this.resolvePathVariables(origin_path, apiData);
      }
      const originValue = resolvedPath
        ? this.getNestedValue(apiData, resolvedPath)
        : value;
      processedValue = originValue;
      // 2. 应用 to_form 转换
      if (to_form) {
        // 映射转换（优先处理）
        if (to_form.mapping) {
          // 遍历映射表，查找匹配的值
          const mappingEntries = Object.entries(to_form.mapping);
          for (const [targetValue, sourceValues] of mappingEntries) {
            // sourceValues 可以是单个值或数组
            const valuesToMatch = Array.isArray(sourceValues)
              ? sourceValues
              : [sourceValues];
            if (valuesToMatch.some((v) => v === processedValue)) {
              // 尝试将 targetValue 转换为合适的类型
              if (targetValue === 'true') {
                processedValue = true;
              } else if (targetValue === 'false') {
                processedValue = false;
              } else if (!isNaN(Number(targetValue))) {
                processedValue = Number(targetValue);
              } else {
                processedValue = targetValue;
              }
              break;
            }
          }
        }
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
            case 'boolean':
              processedValue = Boolean(processedValue);
              break;
          }
        }
      }
    }
    // 提交到API
    if (direction === 'toApi') {
      // 如果没有 to_api 配置，表示不需要处理
      if (!to_api) {
        return value;
      }
      // 映射转换（优先处理）
      if (to_api.mapping) {
        // 遍历映射表，查找匹配的值
        const mappingEntries = Object.entries(to_api.mapping);
        for (const [sourceValue, targetValue] of mappingEntries) {
          // 比较时需要处理类型转换
          const sourceToMatch =
            sourceValue === 'true'
              ? true
              : sourceValue === 'false'
                ? false
                : !isNaN(Number(sourceValue))
                  ? Number(sourceValue)
                  : sourceValue;
          if (processedValue === sourceToMatch) {
            processedValue = targetValue;
            break;
          }
        }
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
      tableColumns?: any[]; // 表格列配置数组，用于处理表格字段加密
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
        const { name, transform_on_create, encrypted } = field;
        let fieldValue = formData[name];
        // 如果字段标记为加密，使用 URL 编码
        if (encrypted && fieldValue) {
          fieldValue = encodeURIComponent(String(fieldValue));
        }
        // 如果有 transform_on_create.mapping 配置，应用映射转换（auto 模式专用）
        if (fieldValue !== undefined && transform_on_create?.mapping) {
          const mappingEntries = Object.entries(transform_on_create.mapping);
          for (const [sourceValue, targetValue] of mappingEntries) {
            // 比较时需要处理类型转换
            const sourceToMatch =
              sourceValue === 'true'
                ? true
                : sourceValue === 'false'
                  ? false
                  : !isNaN(Number(sourceValue))
                    ? Number(sourceValue)
                    : sourceValue;
            if (fieldValue === sourceToMatch) {
              fieldValue = targetValue;
              break;
            }
          }
        }
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
      // 注意：使用 hasOwnProperty 检查而非 falsy 检查，避免空字符串被覆盖
      Object.keys(formData).forEach((key) => {
        if (
          !Object.prototype.hasOwnProperty.call(processedFormData, key) &&
          !fieldsToDelete.includes(key)
        ) {
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
      type // config的type字段
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
        instance_id = this.hashInstanceId(
          this.applyTemplate(context.instance_id, row, context)
        );
      }
      // 过滤掉 key 字段和所有 _error 字段，并处理加密字段
      const cleanedInstanceData = Object.keys(row)
        .filter(
          (fieldKey) => fieldKey !== 'key' && !fieldKey.endsWith('_error')
        )
        .reduce((acc, fieldKey) => {
          let fieldValue = row[fieldKey];
          // 检查该字段是否需要加密（从 tableColumns 中查找配置）
          const fieldConfig = context.tableColumns?.find(
            (f: any) => f.name === fieldKey
          );
          if (fieldConfig?.encrypted && fieldValue) {
            fieldValue = encodeURIComponent(String(fieldValue));
          }
          acc[fieldKey] = fieldValue;
          return acc;
        }, {} as any);

      return {
        ...cleanedInstanceData,
        instance_id,
        node_ids: nodeIds,
        instance_type: context.instance_type
      };
    });

    return {
      collect_type: context.collect_type,
      collector: context.collector,
      configs,
      instances
    };
  }

  /**
   * 使用改进的哈希算法对字符串进行编码
   * 使用 FNV-1a 哈希算法生成64位哈希值，减少碰撞概率
   * 生成固定长度的 base64 字符串（16位），确保相同输入生成相同输出
   */
  static hashInstanceId(id: string): string {
    const instanceId = id || '';
    // FNV-1a 哈希算法 - 生成两个32位哈希值以获得64位哈希
    // 第一个32位哈希
    let hash1 = 2166136261; // FNV offset basis (32-bit)
    for (let i = 0; i < instanceId.length; i++) {
      hash1 ^= instanceId.charCodeAt(i);
      hash1 +=
        (hash1 << 1) +
        (hash1 << 4) +
        (hash1 << 7) +
        (hash1 << 8) +
        (hash1 << 24);
    }
    // 第二个32位哈希（加入字符串长度，确保不同长度的字符串哈希不同）
    let hash2 = 2166136261;
    hash2 ^= instanceId.length; // 将长度纳入哈希
    for (let i = instanceId.length - 1; i >= 0; i--) {
      hash2 ^= instanceId.charCodeAt(i);
      hash2 +=
        (hash2 << 1) +
        (hash2 << 4) +
        (hash2 << 7) +
        (hash2 << 8) +
        (hash2 << 24);
    }
    // 转为无符号32位整数并转为16进制（各8位）
    const hex1 = (hash1 >>> 0).toString(16).padStart(8, '0');
    const hex2 = (hash2 >>> 0).toString(16).padStart(8, '0');
    // 组合成64位哈希的十六进制表示
    const combined = hex1 + hex2;
    // base64 编码
    const b64 = btoa(combined);
    // 去除 '=' 填充符，取前16位（提供更多位数以减少碰撞）
    const result = b64.replace(/=/g, '').slice(0, 16);
    // 如果不足16位，用哈希值的字符填充（理论上不会发生）
    return result.padEnd(16, combined.slice(0, 16 - result.length));
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
   * 解析路径中的变量（如 {{config_id}}）
   * 从 apiData 中查找对应的值进行替换
   */
  static resolvePathVariables(path: string, apiData: any): string {
    let resolvedPath = path;
    // 匹配所有 {{variable}} 格式的变量
    const matches = path.match(/\{\{(\w+)\}\}/g);
    if (matches) {
      matches.forEach((match) => {
        const varName = match.slice(2, -2); // 去掉 {{ 和 }}
        // 尝试从常见位置获取变量值
        let varValue = apiData[varName] || apiData.child?.[varName];
        // 特殊处理：config_id 对应 child.id 的大写形式
        if (varName === 'config_id' && !varValue && apiData.child?.id) {
          varValue = String(apiData.child.id).toUpperCase();
        }
        if (varValue !== undefined) {
          resolvedPath = resolvedPath.replace(match, String(varValue));
        }
      });
    }
    return resolvedPath;
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
