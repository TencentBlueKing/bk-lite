/**
 * 工具调用渲染器
 * 负责生成工具调用和错误消息的 HTML
 * 
 * 设计：所有工具默认收敛成一行提示，点击展开显示工具列表
 * 每个工具显示：状态图标 + 工具名 + 调用目的概要
 * 样式：无深背景、无边框、小字号、简洁紧凑
 */

import { BrowserTaskReceivedData } from '@/app/opspilot/types/global';

export interface ToolCallInfo {
  name: string;
  args: string;
  status: 'calling' | 'completed';
  result?: string;
  browserTaskReceived?: BrowserTaskReceivedData;
}

/**
 * 全局事件委托初始化标记
 */
let cardEventInitialized = false;

const escapeHtml = (text: string) => {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

/**
 * 从工具参数中提取调用目的/概要
 * 尝试多种常见字段名
 */
const extractSummary = (args: string, toolName?: string): string => {
  if (!args || args === '{}' || args === '""' || args === 'null') {
    // 如果没有参数，根据工具名生成默认描述
    return generateDefaultSummary(toolName);
  }
  try {
    const parsed = JSON.parse(args);
    
    // 如果解析后是空对象
    if (typeof parsed === 'object' && parsed !== null && Object.keys(parsed).length === 0) {
      return generateDefaultSummary(toolName);
    }
    
    // 常见的概要/目的字段（按优先级排序）
    const summaryFields = [
      'reason', 'goal', 'thought', 'purpose', 'objective',
      'description', 'summary', 'intent', 'action',
      'query', 'question', 'prompt', 'message', 'content', 'text',
      'command', 'instruction', 'task', 'input'
    ];
    
    for (const field of summaryFields) {
      const value = parsed[field];
      if (typeof value === 'string' && value.trim()) {
        const trimmed = value.trim();
        return trimmed.length > 100 ? trimmed.slice(0, 100) + '...' : trimmed;
      }
    }
    
    // 如果没有找到概要字段，尝试获取第一个有意义的字符串值
    for (const [key, value] of Object.entries(parsed)) {
      // 跳过一些不适合作为概要的字段
      if (['id', 'name', 'type', 'format', 'encoding', 'tool', 'tool_name'].includes(key)) continue;
      if (typeof value === 'string' && value.trim() && value.length >= 3 && value.length < 300) {
        const trimmed = value.trim();
        return trimmed.length > 100 ? trimmed.slice(0, 100) + '...' : trimmed;
      }
    }
    
    // 如果还是没有，尝试将整个参数对象简化显示
    const keys = Object.keys(parsed);
    if (keys.length > 0 && keys.length <= 5) {
      const preview = keys.map(k => {
        const v = parsed[k];
        if (typeof v === 'string') return `${k}: ${v.slice(0, 20)}${v.length > 20 ? '...' : ''}`;
        if (typeof v === 'number' || typeof v === 'boolean') return `${k}: ${v}`;
        return `${k}: ...`;
      }).join(', ');
      if (preview.length > 0) return preview;
    }
  } catch {
    // 解析失败，尝试直接使用 args 字符串
    if (args.length > 3 && args.length < 200) {
      return args.length > 100 ? args.slice(0, 100) + '...' : args;
    }
  }
  return generateDefaultSummary(toolName);
};

/**
 * 根据工具名生成默认描述
 */
const generateDefaultSummary = (toolName?: string): string => {
  if (!toolName) return '';
  
  // 将工具名转换为可读的描述
  // 例如: check_database_health -> 检查数据库健康状态
  //       get_user_info -> 获取用户信息
  const words = toolName.toLowerCase().split(/[_-]/);
  
  // 常见动词映射
  const verbMap: Record<string, string> = {
    'check': '检查',
    'get': '获取',
    'set': '设置',
    'create': '创建',
    'delete': '删除',
    'update': '更新',
    'list': '列出',
    'search': '搜索',
    'find': '查找',
    'query': '查询',
    'fetch': '获取',
    'send': '发送',
    'read': '读取',
    'write': '写入',
    'execute': '执行',
    'run': '运行',
    'start': '启动',
    'stop': '停止',
    'activate': '激活',
    'deactivate': '停用',
    'enable': '启用',
    'disable': '禁用',
    'validate': '验证',
    'verify': '验证',
    'test': '测试',
    'analyze': '分析',
    'process': '处理',
    'generate': '生成',
    'calculate': '计算',
    'convert': '转换',
    'export': '导出',
    'import': '导入',
    'upload': '上传',
    'download': '下载',
    'connect': '连接',
    'disconnect': '断开',
    'open': '打开',
    'close': '关闭',
    'load': '加载',
    'save': '保存',
    'backup': '备份',
    'restore': '恢复',
    'sync': '同步',
    'refresh': '刷新',
    'reset': '重置',
    'clear': '清除',
    'add': '添加',
    'remove': '移除',
    'insert': '插入',
    'append': '追加',
    'merge': '合并',
    'split': '拆分',
    'filter': '过滤',
    'sort': '排序',
    'group': '分组',
    'count': '统计',
    'sum': '求和',
    'avg': '平均',
    'max': '最大',
    'min': '最小'
  };
  
  // 常见名词映射
  const nounMap: Record<string, string> = {
    'database': '数据库',
    'db': '数据库',
    'health': '健康状态',
    'status': '状态',
    'info': '信息',
    'information': '信息',
    'data': '数据',
    'user': '用户',
    'users': '用户',
    'file': '文件',
    'files': '文件',
    'config': '配置',
    'configuration': '配置',
    'setting': '设置',
    'settings': '设置',
    'log': '日志',
    'logs': '日志',
    'error': '错误',
    'errors': '错误',
    'message': '消息',
    'messages': '消息',
    'result': '结果',
    'results': '结果',
    'report': '报告',
    'reports': '报告',
    'list': '列表',
    'table': '表',
    'tables': '表',
    'record': '记录',
    'records': '记录',
    'item': '项目',
    'items': '项目',
    'task': '任务',
    'tasks': '任务',
    'job': '作业',
    'jobs': '作业',
    'process': '进程',
    'service': '服务',
    'services': '服务',
    'server': '服务器',
    'servers': '服务器',
    'client': '客户端',
    'connection': '连接',
    'connections': '连接',
    'session': '会话',
    'sessions': '会话',
    'cache': '缓存',
    'memory': '内存',
    'disk': '磁盘',
    'cpu': 'CPU',
    'network': '网络',
    'metrics': '指标',
    'metric': '指标',
    'performance': '性能',
    'tools': '工具',
    'tool': '工具',
    'cluster': '集群',
    'node': '节点',
    'nodes': '节点',
    'instance': '实例',
    'instances': '实例',
    'resource': '资源',
    'resources': '资源',
    'permission': '权限',
    'permissions': '权限',
    'role': '角色',
    'roles': '角色',
    'group': '组',
    'groups': '组',
    'team': '团队',
    'project': '项目',
    'projects': '项目',
    'api': 'API',
    'endpoint': '端点',
    'url': 'URL',
    'path': '路径',
    'query': '查询',
    'response': '响应',
    'request': '请求',
    'token': '令牌',
    'key': '密钥',
    'secret': '密钥',
    'password': '密码',
    'credential': '凭证',
    'credentials': '凭证',
    'auth': '认证',
    'authentication': '认证',
    'authorization': '授权'
  };
  
  // 尝试翻译
  const translated = words.map(word => {
    if (verbMap[word]) return verbMap[word];
    if (nounMap[word]) return nounMap[word];
    return word;
  });
  
  // 如果第一个词是动词，调整语序
  if (verbMap[words[0]] && translated.length > 1) {
    return translated.join('');
  }
  
  return translated.join(' ');
};

/**
 * 初始化全局事件委托
 */
const initCardEvents = () => {
  if (cardEventInitialized) return;
  cardEventInitialized = true;

  // 只注入 keyframes 动画（展开/折叠由 React onClick handler 处理）
  const styleEl = document.createElement('style');
  styleEl.id = 'tool-call-animations';
  styleEl.textContent = `
    @keyframes tool-spin { 
      0% { transform: rotate(0deg); } 
      100% { transform: rotate(360deg); } 
    }
  `;
  if (!document.getElementById('tool-call-animations')) {
    document.head.appendChild(styleEl);
  }
};

/**
 * 确保事件已初始化
 */
export const initToolCallTooltips = () => {
  if (typeof window !== 'undefined') {
    initCardEvents();
  }
};

/**
 * 同步更新工具调用状态（用于实时更新）
 */
export const syncActiveToolCallPanel = (toolId: string, info: ToolCallInfo) => {
  // 更新单个工具项的状态图标
  const toolItem = document.querySelector(`.tool-call-item[data-tool-id="${CSS.escape(toolId)}"]`) as HTMLElement | null;
  if (toolItem) {
    const statusIcon = toolItem.querySelector('.tool-call-status-icon');
    if (statusIcon) {
      const isCalling = info.status === 'calling';
      if (isCalling) {
        statusIcon.innerHTML = `<span style="display: inline-block; width: 10px; height: 10px; border: 1.5px solid #1677ff; border-top-color: transparent; border-radius: 50%; animation: tool-spin 0.8s linear infinite;"></span>`;
      } else {
        statusIcon.innerHTML = `<span style="color: #52c41a; font-size: 12px;">✓</span>`;
      }
    }
    
    // 更新概要（如果 args 有变化）
    const summarySpan = toolItem.querySelector('.tool-call-summary');
    if (summarySpan) {
      const summary = extractSummary(info.args);
      if (summary) {
        summarySpan.innerHTML = `<span style="color: var(--color-text-3);">· ${escapeHtml(summary)}</span>`;
      }
    }

    // 对 request_user_choice 完成后，在行内追加选择结果 badge
    if (info.name === 'request_user_choice' && info.status === 'completed' && info.result) {
      const existingBadge = toolItem.querySelector('.tool-call-choice-badge');
      if (!existingBadge) {
        const match = info.result.match(/(?:用户回答|选择了|默认选项)[:：]\s*(.+?)(?:[。.]|(?:\s*\(keys:)|$)/);
        const selected = match ? match[1].trim() : '';
        if (selected) {
          const header = toolItem.querySelector('.tool-call-item-header');
          const textSpan = header?.querySelector('span[style*="flex: 1"]');
          if (textSpan) {
            const badge = document.createElement('span');
            badge.className = 'tool-call-choice-badge';
            badge.style.cssText = 'margin-left: 8px; padding: 1px 8px; background: var(--color-primary-light-1, #e6f4ff); color: var(--color-primary-6, #1677ff); border-radius: 10px; font-size: 11px; font-weight: 500;';
            badge.textContent = `→ ${selected}`;
            textSpan.appendChild(badge);
          }
        }
      }
    }
  }

  // 更新组头部的状态
  const group = document.querySelector('.tool-call-group') as HTMLElement | null;
  if (group) {
    const items = group.querySelectorAll('.tool-call-item');
    const completedCount = Array.from(items).filter(item => {
      const icon = item.querySelector('.tool-call-status-icon span');
      return icon && icon.textContent === '✓';
    }).length;
    const totalCount = items.length;

    // 更新组状态图标
    const groupStatusIcon = group.querySelector('.tool-call-group-status');
    if (groupStatusIcon) {
      const hasRunning = completedCount < totalCount;
      if (hasRunning) {
        groupStatusIcon.innerHTML = `<span style="display: inline-block; width: 10px; height: 10px; border: 1.5px solid #1677ff; border-top-color: transparent; border-radius: 50%; animation: tool-spin 0.8s linear infinite;"></span>`;
      } else {
        groupStatusIcon.innerHTML = `<span style="color: #52c41a; font-size: 12px;">✓</span>`;
      }
    }
  }
};

/**
 * 关闭工具调用面板（兼容旧 API）
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const closeActiveToolCallPanel = (_toolId?: string) => {
  // 新设计中不需要关闭单个面板，保留空实现以兼容
};

/**
 * 渲染单个工具项（一行显示：状态 + 工具名 + 概要，点击展开详情）
 */
const renderToolItem = (id: string, info: ToolCallInfo): string => {
  const isCalling = info.status === 'calling';
  const summary = extractSummary(info.args, info.name);

  // 状态图标
  const statusIcon = isCalling
    ? `<span style="display: inline-block; width: 10px; height: 10px; border: 1.5px solid #1677ff; border-top-color: transparent; border-radius: 50%; animation: tool-spin 0.8s linear infinite;"></span>`
    : `<span style="color: #52c41a; font-size: 12px;">✓</span>`;

  // 概要显示（调用目的）- 放在工具名右边
  let summaryHtml = summary 
    ? `<span class="tool-call-summary" style="margin-left: 8px;"><span style="color: var(--color-text-3);">· ${escapeHtml(summary)}</span></span>` 
    : `<span class="tool-call-summary"></span>`;

  // 对 request_user_choice 工具，完成后在行内显示选择结果
  if (info.name === 'request_user_choice' && info.status === 'completed' && info.result) {
    // Match patterns: "用户回答: xxx。" or "选择了: xxx" or "默认选项: xxx。"
    const match = info.result.match(/(?:用户回答|选择了|默认选项)[:：]\s*(.+?)(?:[。.]|(?:\s*\(keys:)|$)/);
    const selected = match ? match[1].trim() : '';
    if (selected) {
      summaryHtml += `<span style="margin-left: 8px; padding: 1px 8px; background: var(--color-primary-light-1, #e6f4ff); color: var(--color-primary-6, #1677ff); border-radius: 10px; font-size: 11px; font-weight: 500;">→ ${escapeHtml(selected)}</span>`;
    }
  }

  // 格式化 JSON 用于详情显示
  const formatJson = (str: string): string => {
    if (!str || str === '{}' || str === '""' || str === 'null') return '';
    try {
      const parsed = JSON.parse(str);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return str;
    }
  };

  // 提取结果中的 content 字段（如果存在）并格式化
  const extractResultContent = (str: string): string => {
    if (!str || str === '{}' || str === '""' || str === 'null') return '';
    
    // 辅助函数：尝试解析并格式化 JSON
    const tryParseAndFormat = (content: string): string | null => {
      // 处理转义字符：将 \n, \t 等字面字符串转换为实际字符
      const unescaped = content
        .replace(/\\n/g, '\n')
        .replace(/\\t/g, '\t')
        .replace(/\\r/g, '\r')
        .replace(/\\"/g, '"')
        .replace(/\\'/g, "'");
      
      try {
        const parsed = JSON.parse(unescaped);
        return JSON.stringify(parsed, null, 2);
      } catch {
        // 如果解析失败，返回处理过转义的内容
        return null;
      }
    };
    
    // 首先尝试解析为 JSON
    try {
      const parsed = JSON.parse(str);
      // 如果有 content 字段，只返回 content 的内容
      if (parsed && typeof parsed === 'object' && 'content' in parsed) {
        const content = parsed.content;
        // content 可能是字符串或对象
        if (typeof content === 'string') {
          const formatted = tryParseAndFormat(content);
          return formatted || content;
        } else {
          return JSON.stringify(content, null, 2);
        }
      }
      // 没有 content 字段，返回整个对象
      return JSON.stringify(parsed, null, 2);
    } catch {
      // JSON 解析失败，尝试提取 Python repr 格式的 content
      // 格式: content='...' name='...' tool_call_id='...'
      
      // 匹配 content='...' 或 content="..."，捕获到 name= 或 tool_call_id= 之前的内容
      let content = '';
      
      // 查找 content= 的位置
      const contentStart = str.indexOf('content=');
      if (contentStart !== -1) {
        // 找到 content= 后面的引号类型
        const afterEqual = str.substring(contentStart + 8);
        const quoteChar = afterEqual[0];
        
        if (quoteChar === "'" || quoteChar === '"') {
          // 找到匹配的结束位置（考虑到内容中可能有嵌套的引号）
          let depth = 0;
          let endPos = 1;
          for (let i = 1; i < afterEqual.length; i++) {
            const char = afterEqual[i];
            if (char === '{' || char === '[') depth++;
            else if (char === '}' || char === ']') depth--;
            else if (char === quoteChar && depth === 0 && afterEqual[i - 1] !== '\\') {
              endPos = i;
              break;
            }
          }
          content = afterEqual.substring(1, endPos);
        } else {
          // 没有引号，找到空格或结尾
          const spacePos = afterEqual.search(/\s+(?:name=|tool_call_id=)/);
          content = spacePos !== -1 ? afterEqual.substring(0, spacePos) : afterEqual;
        }
      }
      
      if (content) {
        const formatted = tryParseAndFormat(content);
        if (formatted) return formatted;
        
        // 如果不是 JSON，至少处理转义字符
        return content
          .replace(/\\n/g, '\n')
          .replace(/\\t/g, '\t')
          .replace(/\\r/g, '\r')
          .replace(/\\"/g, '"')
          .replace(/\\'/g, "'");
      }
      
      // 都失败了，返回原始字符串
      return str;
    }
  };

  // 详情内容：参数和结果
  const argsFormatted = formatJson(info.args);
  const resultFormatted = info.result ? extractResultContent(info.result) : '';
  
  let detailContent = '';
  if (argsFormatted) {
    detailContent += `<div style="margin-bottom: 8px;"><div style="font-weight: 500; color: var(--color-text-2); margin-bottom: 4px;">参数:</div><pre style="margin: 0; padding: 8px; background: var(--color-fill-2); border-radius: 4px; font-size: 11px; overflow-x: auto; white-space: pre-wrap; word-break: break-word;">${escapeHtml(argsFormatted)}</pre></div>`;
  }
  if (resultFormatted) {
    detailContent += `<div><div style="font-weight: 500; color: var(--color-text-2); margin-bottom: 4px;">结果:</div><pre style="margin: 0; padding: 8px; background: var(--color-fill-2); border-radius: 4px; font-size: 11px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow-y: auto;">${escapeHtml(resultFormatted)}</pre></div>`;
  }

  // 如果没有详情内容，不显示展开图标
  const hasDetail = detailContent.length > 0;
  const expandIcon = hasDetail 
    ? `<span class="tool-call-item-expand-icon" style="font-size: 8px; width: 12px; display: inline-flex; align-items: center; justify-content: center; color: var(--color-text-4);">▶</span>`
    : `<span style="width: 12px;"></span>`;

  const header = `<div class="tool-call-item-header" style="display: flex; align-items: center; gap: 6px; padding: 4px 0;"><span class="tool-call-status-icon" style="flex-shrink: 0; width: 16px; display: inline-flex; align-items: center; justify-content: center;">${statusIcon}</span>${expandIcon}<span style="flex: 1; min-width: 0; font-size: 12px; line-height: 1.5;"><span style="color: var(--color-text-1); font-weight: 500;">${escapeHtml(info.name)}</span>${summaryHtml}</span></div>`;

  const detail = hasDetail 
    ? `<div class="tool-call-item-detail" style="padding-left: 34px; font-size: 12px; display: none;">${detailContent}</div>`
    : '';

  return `<div class="tool-call-item" data-tool-id="${escapeHtml(id)}" data-has-detail="${hasDetail}">${header}${detail}</div>`;
};

/**
 * 渲染单个工具调用卡片（兼容旧 API）
 */
export const renderToolCallCard = (id: string, info: ToolCallInfo): string => {
  return renderToolItem(id, info);
};

/**
 * 渲染所有工具调用（回复过程中默认展开，回复结束后收起）
 * @param toolCalls 工具调用信息
 * @param isStreaming 是否正在流式回复中（可选，默认根据工具状态判断）
 */
/**
 * 同批次去重：合并 (工具名 + 参数) 完全相同的重复调用，只保留信息最完整的一个。
 * LLM 偶尔在一条消息里并行发出多个完全相同的工具调用（如 3 个相同的 generate_repair_report），
 * 流式层会为每个 tool_call_id 各发一个 TOOL_CALL_START → 渲染出多张重复卡片。
 * 这里在渲染汇聚点统一去重，实时/历史、流式/非流式全覆盖。
 */
const dedupeToolCallsBySignature = (entries: Array<[string, ToolCallInfo]>): Array<[string, ToolCallInfo]> => {
  const sigToEntry = new Map<string, [string, ToolCallInfo]>();
  const completeness = (info: ToolCallInfo) => (info.status === 'completed' ? 1 : 0) + (info.result ? 1 : 0);

  for (const [id, info] of entries) {
    const sig = `${info.name}::${info.args || ''}`;
    const existing = sigToEntry.get(sig);
    if (!existing) {
      sigToEntry.set(sig, [id, info]);
    } else if (completeness(info) > completeness(existing[1])) {
      // 保留已完成 / 带结果的那个，避免把真正执行过的调用合并丢失
      sigToEntry.set(sig, [id, info]);
    }
  }

  return Array.from(sigToEntry.values());
};

export const renderAllToolCalls = (toolCalls: Map<string, ToolCallInfo>, isStreaming?: boolean): string => {
  if (toolCalls.size === 0) return '';

  const toolsArray = dedupeToolCallsBySignature(Array.from(toolCalls.entries()));
  const totalCount = toolsArray.length;
  const completedCount = toolsArray.filter(([, info]) => info.status === 'completed').length;
  const hasRunning = completedCount < totalCount;

  // 如果传入了 isStreaming 参数，使用它；否则根据工具状态判断
  const shouldExpand = isStreaming !== undefined ? isStreaming : hasRunning;

  // 组头部状态图标
  const groupStatusIcon = hasRunning
    ? `<span style="display: inline-block; width: 10px; height: 10px; border: 1.5px solid #1677ff; border-top-color: transparent; border-radius: 50%; animation: tool-spin 0.8s linear infinite;"></span>`
    : `<span style="color: #52c41a; font-size: 12px;">✓</span>`;

  // 渲染所有工具项
  const toolItems = toolsArray.map(([id, info]) => renderToolItem(id, info)).join('');

  // 提示文字：流式回复中显示"执行中"，完成后显示"点击展开查看详情"
  const hintText = shouldExpand ? '执行中...' : '点击展开查看详情';

  // 组头部
  const header = `<div class="tool-call-group-header" style="display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; cursor: pointer; user-select: none; font-size: 12px; color: var(--color-text-3); border-radius: 4px; margin: 2px 0;"><span class="tool-call-expand-icon" style="font-size: 8px; width: 12px; display: inline-flex; align-items: center; justify-content: center;">▶</span><span class="tool-call-group-status" style="display: inline-flex; align-items: center;">${groupStatusIcon}</span><span>已调用 ${totalCount} 个工具</span><span style="color: var(--color-text-4);">${hintText}</span></div>`;

  // 组内容 - 默认收起时用 display:none，避免 CSS 优先级问题
  const bodyDisplay = shouldExpand ? '' : 'display: none;';
  const body = `<div class="tool-call-group-body" style="padding-left: 20px; margin-top: 4px; ${bodyDisplay}">${toolItems}</div>`;

  // 流式回复中默认展开，回复结束后收起
  const expandedClass = shouldExpand ? ' expanded' : '';

  return `<div class="tool-call-group${expandedClass}" style="margin: 4px 0;">${header}${body}</div>`;
};

/**
 * 渲染错误消息卡片
 */
export const renderErrorMessage = (error: string, type: 'error' | 'run_error' = 'error', code?: string): string => {
  const bgColor = 'rgba(255, 77, 79, 0.05)';
  const textColor = '#ff4d4f';
  const icon = type === 'run_error' ? '⚠️' : '❌';
  const title = type === 'run_error' ? '运行错误' : '错误';
  const codeDisplay = code ? ` (${code})` : '';
  // 移除连续空行，避免破坏 HTML 块解析
  const sanitizedError = error.replace(/\n\s*\n/g, '\n');

  return `<div style="margin: 4px 0; padding: 8px 12px; background: ${bgColor}; border-radius: 6px; font-size: 12px;"><div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;"><span>${icon}</span><span style="color: ${textColor}; font-weight: 500;">${title}${codeDisplay}</span></div><pre style="margin: 0; font-family: monospace; font-size: 11px; color: var(--color-text-2); white-space: pre-wrap; word-break: break-word;">${escapeHtml(sanitizedError)}</pre></div>`;
};
