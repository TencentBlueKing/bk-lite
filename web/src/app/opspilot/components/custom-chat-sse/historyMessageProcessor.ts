/**
 * 历史消息内容处理器
 * 用于将历史会话中的 AG-UI 协议消息解析并渲染为 HTML
 */

import { renderToolCallCard, renderErrorMessage, ToolCallInfo } from './toolCallRenderer';

/**
 * 处理历史消息中的 bot 内容
 * 解析 AG-UI 协议消息数组，渲染文本和工具调用
 * @param content 原始消息内容（可能是 JSON 字符串）
 * @param role 消息角色
 * @returns 处理后的 HTML 内容
 */
export const processHistoryMessageContent = (content: string, role: string): string => {
  // 非 bot 消息直接返回
  if (role !== 'bot') return content;
  
  try {
    // 尝试解析为 JSON 数组
    const parsedContent = JSON.parse(content.replace(/'/g, '"'));
    if (!Array.isArray(parsedContent)) return content;
    
    const parts: string[] = [];
    const toolCalls = new Map<string, ToolCallInfo>();
    let currentText = '';
    let lastBlockType: string | null = null;
    
    // 遍历所有事件消息
    parsedContent.forEach((msg: any) => {
      switch (msg.type) {
        case 'TEXT_MESSAGE_CONTENT':
          // 累积文本内容
          currentText += msg.delta || '';
          break;
          
        case 'TOOL_CALL_START':
          // 工具调用开始，先提交累积的文本
          if (currentText) {
            if (parts.length > 0 && lastBlockType !== 'text') {
              parts.push('\n\n' + currentText);
            } else {
              parts.push(currentText);
            }
            currentText = '';
            lastBlockType = 'text';
          }
          // 初始化工具调用信息（历史记录中默认已完成）
          toolCalls.set(msg.toolCallId, {
            name: msg.toolCallName,
            args: '',
            status: 'completed',
            result: undefined
          });
          break;
          
        case 'TOOL_CALL_ARGS':
          // 累积工具参数
          if (msg.toolCallId) {
            const tool = toolCalls.get(msg.toolCallId);
            if (tool) {
              tool.args += msg.delta || '';
            }
          }
          break;
          
        case 'TOOL_CALL_RESULT':
          // 记录工具执行结果
          if (msg.toolCallId) {
            const tool = toolCalls.get(msg.toolCallId);
            if (tool) {
              tool.result = msg.content || '';
              tool.status = 'completed';
            }
          }
          break;
          
        case 'TOOL_CALL_END':
          // 工具调用结束，渲染工具卡片
          if (msg.toolCallId) {
            const tool = toolCalls.get(msg.toolCallId);
            if (tool) {
              // 使用统一的渲染函数
              const toolCard = renderToolCallCard(msg.toolCallId, tool);
              // 工具调用之间直接拼接，不加换行
              if (parts.length > 0 && lastBlockType === 'toolCall') {
                parts.push(toolCard);
              } else if (parts.length > 0) {
                parts.push('\n\n' + toolCard);
              } else {
                parts.push(toolCard);
              }
              lastBlockType = 'toolCall';
            }
          }
          break;
          
        case 'RUN_ERROR':
        case 'ERROR':
          // 处理错误消息
          if (currentText) {
            parts.push(currentText);
            currentText = '';
          }
          const errorMessage = msg.message || '执行过程中发生错误';
          const errorHtml = renderErrorMessage(errorMessage, msg.type === 'RUN_ERROR' ? 'run_error' : 'error', msg.code);
          if (parts.length > 0) {
            parts.push('\n\n' + errorHtml);
          } else {
            parts.push(errorHtml);
          }
          lastBlockType = 'error';
          break;
          
        default:
          // 忽略其他类型的消息
          break;
      }
    });
    
    // 添加剩余的文本内容
    if (currentText) {
      if (parts.length > 0 && lastBlockType !== 'text') {
        parts.push('\n\n' + currentText);
      } else {
        parts.push(currentText);
      }
    }
    
    return parts.join('');
  } catch (e) {
    // 解析失败，返回原内容
    console.warn('Failed to parse bot message content:', e);
    return content;
  }
};

/**
 * 批量处理历史消息列表
 * @param messages 原始消息数组
 * @returns 处理后的消息数组
 */
export const processHistoryMessages = (messages: any[]): any[] => {
  return messages.map(msg => ({
    ...msg,
    content: processHistoryMessageContent(msg.content, msg.role)
  }));
};
