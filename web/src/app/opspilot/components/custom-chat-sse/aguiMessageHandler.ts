/**
 * AG-UI 协议消息处理器
 * 负责处理不同类型的 AG-UI 消息
 */

import {
  AgentStepProgressValue,
  AGUIMessage,
  ApprovalRequestValue,
  BrowserStepProgressValue,
  BrowserTaskReceivedValue,
  ConfigAnalysisReportValue,
  ConfigAnalysisReportItemValue,
  ConfigAnalysisRecommendationValue,
  ConfigAnalysisSeveritySectionValue,
  StructuredConfigAnalysisReportValue,
  ConfigDiffReportValue,
  RepairCommandsValue,
  ReportFileDownloadValue,
  SubAgentProgressValue,
  UserChoiceRequestValue
} from '@/app/opspilot/types/chat';
import {
  AgentStepProgressData,
  ApprovalRequest,
  BrowserStepProgressData,
  BrowserStepsHistory,
  ConfigAnalysisReport,
  ConfigAnalysisRecommendation,
  ConfigDiffReport,
  CustomChatMessage,
  RepairCommands,
  ReportFileDownload,
  UserChoiceRequest
} from '@/app/opspilot/types/global';
import {
  closeActiveToolCallPanel,
  initToolCallTooltips,
  renderAllToolCalls,
  renderErrorMessage,
  syncActiveToolCallPanel,
  ToolCallInfo
} from './toolCallRenderer';

export interface MessageUpdateFn {
  (updater: (prevMessages: CustomChatMessage[]) => CustomChatMessage[]): void;
}

// 内容块类型
type ContentBlock =
  | { type: 'text'; content: string }
  | { type: 'toolCall'; id: string }
  | { type: 'thinking' }
  | { type: 'configDiff'; reportId: string }
  | { type: 'configAnalysis'; reportId: string }
  | { type: 'fileDownload'; downloadId: string }
  | { type: 'repairCommands'; commandsId: string }
  | { type: 'userChoice'; choiceId: string };

const normalizeConfigAnalysisIssues = (
  section: ConfigAnalysisSeveritySectionValue
): ConfigAnalysisReportItemValue[] => {
  if (Array.isArray(section.issues)) {
    return section.issues;
  }

  if (Array.isArray(section.items)) {
    return section.items;
  }

  return [];
};

export const normalizeConfigAnalysisSection = (
  section: ConfigAnalysisSeveritySectionValue
): ConfigAnalysisSeveritySectionValue => ({
  ...section,
  issues: normalizeConfigAnalysisIssues(section),
});

export const normalizeConfigAnalysisRecommendations = (
  recommendations: ConfigAnalysisRecommendationValue[] | undefined
): ConfigAnalysisRecommendation[] => {
  if (!Array.isArray(recommendations)) {
    return [];
  }

  return recommendations
    .map((recommendation): ConfigAnalysisRecommendation | null => {
      if (!recommendation || typeof recommendation !== 'object') {
        return null;
      }

      const priority = typeof recommendation.priority === 'string' && ['P0', 'P1', 'P2', 'P3'].includes(recommendation.priority)
        ? recommendation.priority as ConfigAnalysisRecommendation['priority']
        : null;
      const action = typeof recommendation.action === 'string' ? recommendation.action.trim() : '';
      const target = typeof recommendation.target === 'string' ? recommendation.target.trim() : '';
      const benefit = typeof recommendation.benefit === 'string' ? recommendation.benefit.trim() : '';

      if (!priority || !action || !target || !benefit) {
        return null;
      }

      return {
        priority,
        action,
        target,
        benefit,
      };
    })
    .filter((recommendation): recommendation is ConfigAnalysisRecommendation => Boolean(recommendation));
};

export const isStructuredConfigAnalysisReport = (
  value: ConfigAnalysisReportValue
): value is StructuredConfigAnalysisReportValue => (
  Boolean(value.report_id) &&
  Boolean(value.title) &&
  Boolean(value.cluster_name) &&
  value.summary !== undefined &&
  Array.isArray(value.severity_sections) &&
  Array.isArray(value.recommendations) &&
  typeof value.markdown === 'string'
);

export class AGUIMessageHandler {
  private contentBlocks: ContentBlock[] = [];
  private currentTextBlock: string = '';
  private thinkingContent: string = '';
  private isThinking: boolean = false;
  private isStreaming: boolean = true;  // 流式回复状态，默认为 true
  private toolCallsRef: Map<string, ToolCallInfo>;
  private botMessage: CustomChatMessage;
  private updateMessages: MessageUpdateFn;
  private browserStepsHistory: BrowserStepProgressData[] = [];
  private approvalRequests: ApprovalRequest[] = [];
  private userChoiceRequests: UserChoiceRequest[] = [];
  private configDiffReports: ConfigDiffReport[] = [];
  private configAnalysisReports: ConfigAnalysisReport[] = [];
  private reportFileDownloads: ReportFileDownload[] = [];
  private repairCommandsList: RepairCommands[] = [];
  private agentStepProgressList: AgentStepProgressData[] = [];

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
    isThinking?: boolean,
    agentStepProgress?: AgentStepProgressData[]
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
            agentStepProgress: agentStepProgress !== undefined ? agentStepProgress : msgItem.agentStepProgress,
            approvalRequests: this.approvalRequests.length > 0
              ? this.approvalRequests.map(req => {
                // 保留用户已做出的决策状态，不被 SSE 更新覆盖
                const existing = msgItem.approvalRequests?.find(r => r.tool_call_id === req.tool_call_id);
                return existing && existing.status !== 'pending' ? existing : req;
              })
              : msgItem.approvalRequests,
            userChoiceRequests: this.userChoiceRequests.length > 0
              ? this.userChoiceRequests.map(req => {
                // 保留用户已做出的选择状态，不被 SSE 更新覆盖
                const existing = msgItem.userChoiceRequests?.find(r => r.choice_id === req.choice_id);
                return existing && existing.status !== 'pending' ? existing : req;
              })
              : msgItem.userChoiceRequests,
            configDiffReports: this.configDiffReports.length > 0
              ? this.configDiffReports
              : msgItem.configDiffReports,
            configAnalysisReports: this.configAnalysisReports.length > 0
              ? this.configAnalysisReports
              : msgItem.configAnalysisReports,
            reportFileDownloads: this.reportFileDownloads.length > 0
              ? this.reportFileDownloads
              : msgItem.reportFileDownloads,
            repairCommands: this.repairCommandsList.length > 0
              ? this.repairCommandsList
              : msgItem.repairCommands,
            updateAt: new Date().toISOString()
          }
          : msgItem
      )
    );
  }

  /**
   * 获取完整内容 - 按照内容块的顺序渲染
   * 连续的工具调用会被合并成一个可折叠的组
   */
  private getFullContent(): string {
    const parts: string[] = [];
    let lastBlockType: string | null = null;
    let pendingToolCalls: Map<string, ToolCallInfo> = new Map();

    const flushToolCalls = () => {
      if (pendingToolCalls.size > 0) {
        // 传入 isStreaming 状态，控制工具列表是否展开
        const toolCallsHtml = renderAllToolCalls(pendingToolCalls, this.isStreaming);
        if (parts.length > 0) {
          parts.push('\n\n' + toolCallsHtml);
        } else {
          parts.push(toolCallsHtml);
        }
        pendingToolCalls = new Map();
        lastBlockType = 'toolCall';
      }
    };

    for (const block of this.contentBlocks) {
      if (block.type === 'text') {
        // 遇到文本块，先输出累积的工具调用
        flushToolCalls();
        if (parts.length > 0) {
          parts.push('\n\n' + block.content);
        } else {
          parts.push(block.content);
        }
        lastBlockType = 'text';
      } else if (block.type === 'toolCall') {
        // 累积工具调用
        const toolInfo = this.toolCallsRef.get(block.id);
        if (toolInfo) {
          pendingToolCalls.set(block.id, toolInfo);
        }
      } else if (block.type === 'configDiff') {
        flushToolCalls();
        // Insert placeholder marker for React component rendering
        parts.push(`\n\n<!--CONFIG_DIFF:${block.reportId}-->`);
        lastBlockType = 'configDiff';
      } else if (block.type === 'configAnalysis') {
        flushToolCalls();
        parts.push(`\n\n<!--CONFIG_ANALYSIS:${block.reportId}-->`);
        lastBlockType = 'configAnalysis';
      } else if (block.type === 'fileDownload') {
        flushToolCalls();
        // File download cards are rendered via reportFileDownloads, no inline marker needed
        lastBlockType = 'fileDownload';
      } else if (block.type === 'repairCommands') {
        flushToolCalls();
        // Repair commands rendered via repairCommands data, no inline marker needed
        lastBlockType = 'repairCommands';
      } else if (block.type === 'userChoice') {
        flushToolCalls();
        // Insert placeholder marker for React component rendering
        parts.push(`\n\n<!--USER_CHOICE:${block.choiceId}-->`);
        lastBlockType = 'userChoice';
      } else if (block.type === 'thinking') {
        // 忽略 thinking 块
      }
    }

    // 输出剩余的工具调用
    flushToolCalls();

    // 添加当前正在累积的文本
    if (this.currentTextBlock) {
      if (parts.length > 0 && lastBlockType !== 'text') {
        parts.push('\n\n' + this.currentTextBlock);
      } else if (parts.length > 0) {
        parts.push(this.currentTextBlock);
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
      this.syncAttachmentDownloadFromToolResult(toolCallId, toolCall.name, content);

      // Fallback: if report_config_diff completed but CUSTOM event wasn't received,
      // construct the DiffReportCard from tool args
      if (toolCall.name === 'report_config_diff' && toolCall.args) {
        try {
          const args = JSON.parse(toolCall.args);
          const existingReport = this.configDiffReports.find(
            r => r.cluster_name === args.cluster_name && r.title === args.title
          );
          if (!existingReport && args.items && args.items.length > 0) {
            const report: ConfigDiffReport = {
              report_id: `fallback_${toolCallId}`,
              title: args.title || '',
              cluster_name: args.cluster_name || '',
              items: args.items,
              received_at: Date.now(),
            };
            this.configDiffReports.push(report);
            this.flushCurrentTextBlock();
            this.contentBlocks.push({ type: 'configDiff', reportId: report.report_id });
          }
        } catch {
          // args parse failed, skip fallback
        }
      }

      closeActiveToolCallPanel(toolCallId);
      this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
    }
  }

  private syncAttachmentDownloadFromToolResult(toolCallId: string, toolName: string, content: string) {
    if (toolName !== 'generate_attachment_file') {
      return;
    }

    try {
      const parsed = this.parseAttachmentToolResult(content);
      if (!parsed?.file_url || !parsed?.filename) {
        return;
      }

      const downloadId = `attachment_${toolCallId}`;
      const existed = this.reportFileDownloads.some(download => download.download_id === downloadId);
      if (existed) {
        return;
      }

      this.reportFileDownloads.push({
        download_id: downloadId,
        filename: parsed.filename,
        file_url: parsed.file_url,
        mime_type: parsed.mime_type || 'application/octet-stream',
        received_at: Date.now(),
      });
      this.flushCurrentTextBlock();
      this.contentBlocks.push({ type: 'fileDownload', downloadId });
    } catch {
      // ignore invalid tool result payloads
    }
  }

  private parseAttachmentToolResult(content: string) {
    try {
      return JSON.parse(content);
    } catch {
      const extractField = (field: string) => {
        const match = content.match(new RegExp(`[\"']${field}[\"']\\s*:\\s*[\"']([^\"']+)[\"']`));
        return match?.[1];
      };

      return {
        filename: extractField('filename'),
        file_url: extractField('file_url'),
        mime_type: extractField('mime_type'),
      };
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

  handleAgentStepProgress(value: AgentStepProgressValue) {
    const data = value as AgentStepProgressData;
    // Update or append based on agent_name + step
    const key = `${data.agent_name || 'main'}_${data.step}`;
    const existingIdx = this.agentStepProgressList.findIndex(
      d => `${d.agent_name || 'main'}_${d.step}` === key
    );
    if (existingIdx >= 0) {
      this.agentStepProgressList[existingIdx] = data;
    } else {
      this.agentStepProgressList.push(data);
    }
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking, this.agentStepProgressList);
  }

  handleSubAgentProgress(value: SubAgentProgressValue) {
    const data: AgentStepProgressData = {
      agent_name: value.agent_name,
      step: 0,
      max_steps: 0,
      status: value.status,
      description: value.description,
    };
    // For sub-agent lifecycle events, upsert by agent_name
    const existingIdx = this.agentStepProgressList.findIndex(
      d => d.agent_name === value.agent_name && (d.status === 'started' || d.status === 'running')
    );
    if (existingIdx >= 0 && (value.status === 'completed' || value.status === 'error')) {
      this.agentStepProgressList[existingIdx] = data;
    } else {
      this.agentStepProgressList.push(data);
    }
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking, this.agentStepProgressList);
  }

  /**
   * 处理审批请求事件
   */
  handleApprovalRequest(value: ApprovalRequestValue) {
    const request: ApprovalRequest = {
      ...value,
      received_at: Date.now(),
      status: 'pending',
    };
    this.approvalRequests.push(request);
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  /**
   * 更新审批请求状态
   */
  updateApprovalStatus(toolCallId: string, status: 'approved' | 'rejected') {
    const request = this.approvalRequests.find(r => r.tool_call_id === toolCallId);
    if (request) {
      request.status = status;
      this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
    }
  }

  /**
   * 处理用户选择请求事件
   */
  handleUserChoiceRequest(value: UserChoiceRequestValue) {
    const request: UserChoiceRequest = {
      ...value,
      received_at: Date.now(),
      status: 'pending',
    };
    this.userChoiceRequests.push(request);
    // Insert a placeholder block so the card renders in-order
    this.flushCurrentTextBlock();
    this.contentBlocks.push({ type: 'userChoice', choiceId: request.choice_id });
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  /**
   * 更新用户选择请求状态
   */
  updateUserChoiceStatus(choiceId: string, status: 'submitted' | 'timeout', selected?: string[]) {
    const request = this.userChoiceRequests.find(r => r.choice_id === choiceId);
    if (request) {
      request.status = status;
      if (selected) {
        request.selected = selected;
      }
      this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
    }
  }

  /**
   * 处理用户选择结果事件（来自后端超时或自动选择）
   */
  handleUserChoiceResult(value: { choice_id: string; selected: string[]; source: string }) {
    const status = value.source === 'user' ? 'submitted' : 'timeout';
    this.updateUserChoiceStatus(value.choice_id, status, value.selected);
  }

  /**
   * 处理配置 diff 报告事件
   */
  handleConfigDiffReport(value: ConfigDiffReportValue) {
    const report: ConfigDiffReport = {
      ...value,
      received_at: Date.now(),
    };
    this.configDiffReports.push(report);
    // Insert a placeholder block so the card renders in-order
    this.flushCurrentTextBlock();
    this.contentBlocks.push({ type: 'configDiff', reportId: report.report_id });
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  handleConfigAnalysisReport(value: ConfigAnalysisReportValue) {
    this.flushCurrentTextBlock();

    if (isStructuredConfigAnalysisReport(value)) {
      const existingIndex = this.configAnalysisReports.findIndex(
        report => report.report_id === value.report_id
      );
      const severity_sections = value.severity_sections.map(normalizeConfigAnalysisSection);
      const report: ConfigAnalysisReport = {
        ...value,
        summary: value.summary || {},
        severity_sections,
        recommendations: normalizeConfigAnalysisRecommendations(value.recommendations),
        markdown: value.markdown,
        fallback_markdown: value.fallback_markdown || value.markdown,
        received_at: Date.now(),
      };

      if (existingIndex >= 0) {
        this.configAnalysisReports[existingIndex] = report;
      } else {
        this.configAnalysisReports.push(report);
      }

      const hasMarker = this.contentBlocks.some(
        block => block.type === 'configAnalysis' && block.reportId === value.report_id
      );
      if (!hasMarker) {
        this.contentBlocks.push({ type: 'configAnalysis', reportId: value.report_id });
      }
    } else {
      const fallbackMarkdown = value.fallback_markdown || value.markdown;
      if (fallbackMarkdown) {
        this.contentBlocks.push({ type: 'text', content: fallbackMarkdown });
      }
    }

    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  /**
   * 处理报告文件下载事件
   */
  handleReportFileDownload(value: ReportFileDownloadValue) {
    const download: ReportFileDownload = {
      ...value,
      received_at: Date.now(),
    };
    this.reportFileDownloads.push(download);
    this.flushCurrentTextBlock();
    this.contentBlocks.push({ type: 'fileDownload', downloadId: download.download_id });
    this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, this.isThinking);
  }

  /**
   * 处理修复命令事件
   */
  handleRepairCommands(value: RepairCommandsValue) {
    const commands: RepairCommands = {
      ...value,
      received_at: Date.now(),
    };
    this.repairCommandsList.push(commands);
    this.flushCurrentTextBlock();
    this.contentBlocks.push({ type: 'repairCommands', commandsId: commands.commands_id });
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
        // 流式回复结束，设置 isStreaming 为 false 并更新内容（收起工具列表）
        this.isStreaming = false;
        this.handleBrowserStepComplete();
        // 重新渲染内容以收起工具列表
        this.updateMessageContent(this.getFullContent(), undefined, undefined, this.thinkingContent, false);
        return true;

      case 'CUSTOM':
        if (aguiData.name === 'browser_step_progress' && aguiData.value) {
          this.handleBrowserStepProgress(aguiData.value as BrowserStepProgressValue);
        } else if (aguiData.name === 'browser_task_received' && aguiData.value) {
          this.handleBrowserTaskReceived(aguiData.value as BrowserTaskReceivedValue);
        } else if (aguiData.name === 'approval_request' && aguiData.value) {
          this.handleApprovalRequest(aguiData.value as ApprovalRequestValue);
        } else if (aguiData.name === 'user_choice_request' && aguiData.value) {
          this.handleUserChoiceRequest(aguiData.value as UserChoiceRequestValue);
        } else if (aguiData.name === 'user_choice_result' && aguiData.value) {
          this.handleUserChoiceResult(aguiData.value as { choice_id: string; selected: string[]; source: string });
        } else if (aguiData.name === 'config_diff_report' && aguiData.value) {
          this.handleConfigDiffReport(aguiData.value as unknown as ConfigDiffReportValue);
        } else if (aguiData.name === 'config_analysis_report' && aguiData.value) {
          this.handleConfigAnalysisReport(aguiData.value as ConfigAnalysisReportValue);
        } else if (aguiData.name === 'report_file_download' && aguiData.value) {
          this.handleReportFileDownload(aguiData.value as unknown as ReportFileDownloadValue);
        } else if (aguiData.name === 'repair_commands' && aguiData.value) {
          this.handleRepairCommands(aguiData.value as unknown as RepairCommandsValue);
        } else if (aguiData.name === 'agent_step_progress' && aguiData.value) {
          this.handleAgentStepProgress(aguiData.value as AgentStepProgressValue);
        } else if (aguiData.name === 'sub_agent_progress' && aguiData.value) {
          this.handleSubAgentProgress(aguiData.value as SubAgentProgressValue);
        }
        return false;

      default:
        console.warn('[AG-UI] Unknown message type:', aguiData.type);
        return false;
    }
  }
}
