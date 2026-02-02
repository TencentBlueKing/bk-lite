/**
 * AG-UI 协议消息处理器
 * 负责处理不同类型的 AG-UI 消息
 */

import { AGUIMessage } from '@/app/opspilot/types/chat';
import { CustomChatMessage } from '@/app/opspilot/types/global';
import { ToolCallInfo, renderToolCallCard, renderErrorMessage, initToolCallTooltips } from './toolCallRenderer';

export interface MessageUpdateFn {
  (updater: (prevMessages: CustomChatMessage[]) => CustomChatMessage[]): void;
}

// 内容块类型
type ContentBlock = 
  | { type: 'text'; content: string }
  | { type: 'toolCall'; id: string }
  | { type: 'thinking' };

export class AGUIMessageHandler {
  private contentBlocks: ContentBlock[] = [];
  private currentTextBlock: string = '';
  private toolCallsRef: Map<string, ToolCallInfo>;
  private botMessage: CustomChatMessage;
  private updateMessages: MessageUpdateFn;

  constructor(
    botMessage: CustomChatMessage,
    updateMessages: MessageUpdateFn,
    toolCallsRef: Map<string, ToolCallInfo>
  ) {
    this.botMessage = botMessage;
    this.updateMessages = updateMessages;
    this.toolCallsRef = toolCallsRef;
    
    // 初始化 tooltip 事件监听（只在浏览器环境执行一次）
    if (typeof window !== 'undefined') {
      initToolCallTooltips();
    }
  }

  /**
   * 更新消息内容
   */
  private updateMessageContent(content: string) {
    this.updateMessages(prevMessages =>
      prevMessages.map(msgItem =>
        msgItem.id === this.botMessage.id
          ? {
            ...msgItem,
            content,
            updateAt: new Date().toISOString()
          }
          : msgItem
      )
    );
  }

  /**
   * 获取完整内容 - 按照内容块的顺序渲染
   */
  private getFullContent(): string {
    const parts: string[] = [];
    let lastBlockType: string | null = null;

    for (const block of this.contentBlocks) {
      let content = '';
      
      if (block.type === 'text') {
        content = block.content;
      } else if (block.type === 'toolCall') {
        const toolInfo = this.toolCallsRef.get(block.id);
        if (toolInfo) {
          content = renderToolCallCard(block.id, toolInfo);
        }
      } else if (block.type === 'thinking') {
        content = '<div class="thinking-loader" style="display: flex; align-items: center; gap: 8px; color: #999;"><span style="display: inline-flex; gap: 4px;"><span style="width: 8px; height: 8px; background: currentColor; border-radius: 50%; animation: thinking-dot 1.4s infinite ease-in-out both; animation-delay: -0.32s;"></span><span style="width: 8px; height: 8px; background: currentColor; border-radius: 50%; animation: thinking-dot 1.4s infinite ease-in-out both; animation-delay: -0.16s;"></span><span style="width: 8px; height: 8px; background: currentColor; border-radius: 50%; animation: thinking-dot 1.4s infinite ease-in-out both;"></span></span></div><style>@keyframes thinking-dot { 0%, 80%, 100% { transform: scale(0); opacity: 0.5; } 40% { transform: scale(1); opacity: 1; } }</style>';
      }

      if (content) {
        // 工具调用之间不换行，其他情况换行
        if (parts.length > 0) {
          if (lastBlockType === 'toolCall' && block.type === 'toolCall') {
            // 工具调用之间直接拼接，不加换行
            parts.push(content);
          } else {
            // 其他情况加换行
            parts.push('\n\n' + content);
          }
        } else {
          parts.push(content);
        }
        lastBlockType = block.type;
      }
    }

    // 添加当前正在累积的文本
    if (this.currentTextBlock) {
      if (parts.length > 0 && lastBlockType !== 'text') {
        parts.push('\n\n' + this.currentTextBlock);
      } else {
        parts.push(this.currentTextBlock);
      }
    }

    return parts.join('');
  }

  /**
   * 清除"正在思考"提示
   */
  private clearThinkingPrompt() {
    this.contentBlocks = this.contentBlocks.filter(block => block.type !== 'thinking');
  }

  /**
   * 提交当前文本块
   */
  private flushCurrentTextBlock() {
    if (this.currentTextBlock) {
      this.contentBlocks.push({ type: 'text', content: this.currentTextBlock });
      this.currentTextBlock = '';
    }
  }

  /**
   * 处理 RUN_STARTED 事件
   */
  handleRunStarted() {
    this.contentBlocks.push({ type: 'thinking' });
    this.updateMessageContent(this.getFullContent());
  }

  /**
   * 处理 TEXT_MESSAGE_CONTENT 事件
   */
  handleTextContent(delta: string) {
    this.clearThinkingPrompt();
    this.currentTextBlock += delta;
    this.updateMessageContent(this.getFullContent());
  }

  /**
   * 处理 TOOL_CALL_START 事件
   */
  handleToolCallStart(toolCallId: string, toolCallName: string) {
    // 提交当前文本块
    this.flushCurrentTextBlock();
    
    // 添加工具调用块
    this.contentBlocks.push({ type: 'toolCall', id: toolCallId });
    
    this.toolCallsRef.set(toolCallId, {
      name: toolCallName,
      args: '',
      status: 'calling'
    });
    this.updateMessageContent(this.getFullContent());
  }

  /**
   * 处理 TOOL_CALL_ARGS 事件
   */
  handleToolCallArgs(toolCallId: string, delta: string) {
    const toolCall = this.toolCallsRef.get(toolCallId);
    if (toolCall) {
      toolCall.args += delta;
      this.updateMessageContent(this.getFullContent());
    }
  }

  /**
   * 处理 TOOL_CALL_RESULT 事件
   */
  handleToolCallResult(toolCallId: string, content: string) {
    const toolCall = this.toolCallsRef.get(toolCallId);
    if (toolCall) {
      toolCall.status = 'completed';
      toolCall.result = content;
      this.updateMessageContent(this.getFullContent());
    }
  }

  /**
   * 处理 ERROR 事件
   */
  handleError(error: string) {
    this.clearThinkingPrompt();
    this.flushCurrentTextBlock();
    const errorMessage = renderErrorMessage(error, 'error');
    this.contentBlocks.push({ type: 'text', content: errorMessage });
    this.updateMessageContent(this.getFullContent());
  }

  /**
   * 处理 RUN_ERROR 事件
   */
  handleRunError(message: string, code?: string) {
    this.clearThinkingPrompt();
    this.flushCurrentTextBlock();
    const errorMessage = renderErrorMessage(message, 'run_error', code);
    this.contentBlocks.push({ type: 'text', content: errorMessage });
    this.updateMessageContent(this.getFullContent());
  }

  /**
   * 处理消息并返回是否应该停止
   */
  handle(aguiData: AGUIMessage): boolean {
    switch (aguiData.type) {
      case 'RUN_STARTED':
        this.handleRunStarted();
        return false;

      case 'TEXT_MESSAGE_START':
        return false;

      case 'TEXT_MESSAGE_CONTENT':
        if (aguiData.delta) {
          this.handleTextContent(aguiData.delta);
        }
        return false;

      case 'TEXT_MESSAGE_END':
        return false;

      case 'TOOL_CALL_START':
        if (aguiData.toolCallId && aguiData.toolCallName) {
          this.handleToolCallStart(aguiData.toolCallId, aguiData.toolCallName);
        }
        return false;

      case 'TOOL_CALL_ARGS':
        if (aguiData.toolCallId && aguiData.delta) {
          this.handleToolCallArgs(aguiData.toolCallId, aguiData.delta);
        }
        return false;

      case 'TOOL_CALL_END':
        return false;

      case 'TOOL_CALL_RESULT':
        if (aguiData.toolCallId && aguiData.content) {
          this.handleToolCallResult(aguiData.toolCallId, aguiData.content);
        }
        return false;

      case 'ERROR':
        if (aguiData.error) {
          this.handleError(aguiData.error);
        }
        return true;

      case 'RUN_ERROR':
        if (aguiData.message || aguiData.error) {
          const errorContent = aguiData.message || aguiData.error || '未知错误';
          this.handleRunError(errorContent, aguiData.code);
        }
        return true;

      case 'RUN_FINISHED':
        return true;

      default:
        console.warn('[AG-UI] Unknown message type:', aguiData.type);
        return false;
    }
  }
}
