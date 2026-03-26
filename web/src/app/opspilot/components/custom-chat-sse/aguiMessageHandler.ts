/**
 * AG-UI 协议消息处理器
 * 负责处理不同类型的 AG-UI 消息
 */

import { AGUIMessage, BrowserStepProgressValue, BrowserTaskReceivedValue } from '@/app/opspilot/types/chat';
import { CustomChatMessage, BrowserStepProgressData, BrowserStepsHistory } from '@/app/opspilot/types/global';
import { ToolCallInfo, renderToolCallCard, renderErrorMessage, initToolCallTooltips, syncActiveToolCallPanel, closeActiveToolCallPanel } from './toolCallRenderer';

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
  private thinkingContent: string = '';
  private isThinking: boolean = false;
  private toolCallsRef: Map<string, ToolCallInfo>;
  private botMessage: CustomChatMessage;
  private updateMessages: MessageUpdateFn;
  private browserStepsHistory: BrowserStepProgressData[] = [];

  constructor(
    botMessage: CustomChatMessage,
    updateMessages: MessageUpdateFn,
    toolCallsRef: Map<string, ToolCallInfo>
  ) {
    this.botMessage = botMessage;
    this.updateMessages = updateMessages;
    this.toolCallsRef = toolCallsRef;

    if (typeof window !== 'undefined') {
      initToolCallTooltips();
    }
  }

  /**
   * 更新消息内容
   */
  private updateMessageContent(
    content: string,
    browserStepProgress?: BrowserStepProgressData | null,
    browserStepsHistory?: BrowserStepsHistory | null,
    thinking?: string,
    isThinking?: boolean
  ) {
    this.updateMessages(prevMessages =>
      prevMessages.map(msgItem =>
        msgItem.id === this.botMessage.id
          ? {
            ...msgItem,
            content,
            thinking: thinking !== undefined ? thinking : msgItem.thinking,
            isThinking: isThinking !== undefined ? isThinking : msgItem.isThinking,
            browserStepProgress: browserStepProgress !== undefined ? browserStepProgress : msgItem.browserStepProgress,
            browserStepsHistory: browserStepsHistory !== undefined ? browserStepsHistory : msgItem.browserStepsHistory,
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
        content = '';
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

  private stopThinking() {
    this.clearThinkingPrompt();
    this.isThinking = false;
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
    this.isThinking = true;
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  handleThinking(delta: string) {
    if (!this.isThinking) {
      this.isThinking = true;
    }

    this.thinkingContent += delta;
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  /**
   * 处理 TEXT_MESSAGE_CONTENT 事件
   */
  handleTextContent(delta: string) {
    this.stopThinking();
    this.currentTextBlock += delta;
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  /**
   * 处理 TOOL_CALL_START 事件
   */
  handleToolCallStart(toolCallId: string, toolCallName: string) {
    this.stopThinking();
    this.flushCurrentTextBlock();

    this.contentBlocks.push({ type: 'toolCall', id: toolCallId });

    this.toolCallsRef.set(toolCallId, {
      name: toolCallName,
      args: '',
      status: 'calling'
    });
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  /**
   * 处理 TOOL_CALL_ARGS 事件
   */
  handleToolCallArgs(toolCallId: string, delta: string) {
    const toolCall = this.toolCallsRef.get(toolCallId);
    if (toolCall) {
      toolCall.args += delta;
      this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
    }
  }

  private findLatestCallingToolCallId(preferredToolName?: string) {
    const entries = Array.from(this.toolCallsRef.entries()).reverse();

    if (preferredToolName) {
      const matchedEntry = entries.find(([, toolCall]) => toolCall.status === 'calling' && toolCall.name === preferredToolName);
      if (matchedEntry) {
        return matchedEntry[0];
      }
    }

    const latestCallingEntry = entries.find(([, toolCall]) => toolCall.status === 'calling');
    return latestCallingEntry?.[0];
  }

  /**
   * 处理 TOOL_CALL_RESULT 事件
   */
  handleToolCallResult(toolCallId: string, content: string) {
    const toolCall = this.toolCallsRef.get(toolCallId);
    if (toolCall) {
      toolCall.status = 'completed';
      toolCall.result = content;
      closeActiveToolCallPanel(toolCallId);
      this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
    }
  }

  handleBrowserTaskReceived(value: BrowserTaskReceivedValue) {
    const preferredToolName = typeof value.tool === 'string' ? value.tool : undefined;
    const toolCallId = this.findLatestCallingToolCallId(preferredToolName);
    if (!toolCallId) return;

    const toolCall = this.toolCallsRef.get(toolCallId);
    if (!toolCall) return;

    toolCall.browserTaskReceived = value;
    syncActiveToolCallPanel(toolCallId, toolCall);
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  /**
   * 处理 ERROR 事件
   */
  handleError(error: string) {
    this.stopThinking();
    this.flushCurrentTextBlock();
    const errorMessage = renderErrorMessage(error, 'error');
    this.contentBlocks.push({ type: 'text', content: errorMessage });
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  /**
   * 处理 RUN_ERROR 事件
   */
  handleRunError(message: string, code?: string) {
    this.stopThinking();
    this.flushCurrentTextBlock();
    const errorMessage = renderErrorMessage(message, 'run_error', code);
    this.contentBlocks.push({ type: 'text', content: errorMessage });
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  handleBrowserStepProgress(value: BrowserStepProgressValue) {
    this.stopThinking();
    const stepData = value as BrowserStepProgressData;

    const existingIndex = this.browserStepsHistory.findIndex(
      s => s.step_number === stepData.step_number
    );

    if (existingIndex >= 0) {
      this.browserStepsHistory[existingIndex] = stepData;
    } else {
      this.browserStepsHistory.push(stepData);
    }

    this.browserStepsHistory.sort((a, b) => a.step_number - b.step_number);

    const history: BrowserStepsHistory = {
      steps: [...this.browserStepsHistory],
      isRunning: true
    };

    this.updateMessageContent(this.getFullContent(), stepData, history, this.thinkingContent, this.isThinking);
  }

  handleBrowserStepComplete() {
    this.clearThinkingPrompt();
    this.isThinking = false;
    if (this.browserStepsHistory.length > 0) {
      const history: BrowserStepsHistory = {
        steps: [...this.browserStepsHistory],
        isRunning: false
      };
      const lastStep = this.browserStepsHistory[this.browserStepsHistory.length - 1];
      this.updateMessageContent(this.getFullContent(), lastStep, history, this.thinkingContent, this.isThinking);
    } else {
      this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
    }
  }

  /**
   * 处理消息并返回是否应该停止
   */
  handle(aguiData: AGUIMessage): boolean {
    switch (aguiData.type) {
      case 'RUN_STARTED':
        this.handleRunStarted();
        return false;

      case 'THINKING':
        if (aguiData.delta) {
          this.handleThinking(aguiData.delta);
        }
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
        this.handleBrowserStepComplete();
        return true;

      case 'CUSTOM':
        if (aguiData.name === 'browser_step_progress' && aguiData.value) {
          this.handleBrowserStepProgress(aguiData.value as BrowserStepProgressValue);
        } else if (aguiData.name === 'browser_task_received' && aguiData.value) {
          this.handleBrowserTaskReceived(aguiData.value as BrowserTaskReceivedValue);
        }
        return false;

      default:
        console.warn('[AG-UI] Unknown message type:', aguiData.type);
        return false;
    }
  }
}
