/**
 * 解析历史消息中的事件流
 * 从事件数组中提取文本内容、thinking、工具调用等信息
 */

export interface ToolCall {
    id: string;
    name: string;
    args: string;
    result?: string;
    status: 'executing' | 'completed';
}

export interface ContentPart {
    type: 'text' | 'tool_call' | 'component';
    textContent?: string; // 原始 markdown 文本（未渲染）
    segmentIndex?: number; // 文本段索引
    toolCall?: ToolCall;
    component?: {
        name: string;
        props: any;
    };
}

export interface ParsedHistoryMessage {
    fullTextContent: string; // 所有文本段拼接后的完整内容（用于复制功能）
    thinking?: string; // 思考过程内容
    contentParts: ContentPart[]; // 按顺序排列的内容部分
}

/**
 * 解析历史消息事件流
 * @param eventString 事件流字符串（Python 风格的列表）
 * @returns 解析后的消息内容
 */
export function parseHistoryEvents(eventString: string): ParsedHistoryMessage {
    const result: ParsedHistoryMessage = {
        fullTextContent: '',
        contentParts: [],
    };

    try {
        // 将 Python 风格的字符串转换为 JSON
        // 替换单引号为双引号，处理特殊情况
        const jsonString = eventString
            .replace(/'/g, '"')
            .replace(/True/g, 'true')
            .replace(/False/g, 'false')
            .replace(/None/g, 'null');

        const events = JSON.parse(jsonString);

        if (!Array.isArray(events)) {
            console.warn('事件数据不是数组格式');
            return result;
        }

        let thinkingContent = '';
        let fullTextContent = ''; // 用于复制的完整文本
        let currentTextSegmentIndex = 0; // 当前文本段索引
        let currentTextSegment = ''; // 当前文本段的累积内容
        const toolCallMap = new Map<string, ToolCall>();

        // 遍历所有事件
        events.forEach((event: any) => {
            switch (event.type) {
                case 'THINKING_CONTENT':
                    // 累积思考过程内容
                    thinkingContent += event.delta || '';
                    break;

                case 'TEXT_MESSAGE_START':
                    // 新的文本段开始
                    // 如果之前有累积的文本，先保存
                    if (currentTextSegment) {
                        result.contentParts.push({
                            type: 'text',
                            textContent: currentTextSegment,
                            segmentIndex: currentTextSegmentIndex,
                        });
                    }
                    // 重置当前段，准备接收新内容
                    currentTextSegment = '';
                    currentTextSegmentIndex++;
                    break;

                case 'TEXT_MESSAGE_CONTENT':
                    // 累积当前文本段的内容
                    const textDelta = event.delta || event.msg || '';
                    currentTextSegment += textDelta;
                    fullTextContent += textDelta; // 同时累积完整文本
                    break;

                case 'TEXT_MESSAGE_END':
                    // 文本段结束，保存到 contentParts
                    if (currentTextSegment) {
                        result.contentParts.push({
                            type: 'text',
                            textContent: currentTextSegment,
                            segmentIndex: currentTextSegmentIndex,
                        });
                        currentTextSegment = ''; // 清空当前段
                    }
                    break;

                case 'TOOL_CALL_START':
                    // 工具调用开始
                    if (event.toolCallId) {
                        const toolCall: ToolCall = {
                            id: event.toolCallId,
                            name: event.toolCallName || 'Unknown Tool',
                            args: '',
                            status: 'executing',
                        };
                        toolCallMap.set(event.toolCallId, toolCall);
                        // 立即添加到 contentParts（保持顺序）
                        result.contentParts.push({
                            type: 'tool_call',
                            toolCall: toolCall,
                        });
                    }
                    break;

                case 'TOOL_CALL_ARGS':
                    // 累积工具调用参数
                    if (event.toolCallId && toolCallMap.has(event.toolCallId)) {
                        const tool = toolCallMap.get(event.toolCallId)!;
                        tool.args += event.delta || '';
                    }
                    break;

                case 'TOOL_CALL_RESULT':
                    // 记录工具调用结果
                    if (event.toolCallId && toolCallMap.has(event.toolCallId)) {
                        const tool = toolCallMap.get(event.toolCallId)!;
                        tool.result = event.content;
                        tool.status = 'completed';
                    }
                    break;

                case 'CUSTOM':
                    // 自定义组件
                    if (event.name === 'render_component' && event.value) {
                        result.contentParts.push({
                            type: 'component',
                            component: {
                                name: event.value.component,
                                props: event.value.props,
                            },
                        });
                    }
                    break;
            }
        });

        // 处理可能残留的最后一段文本
        if (currentTextSegment) {
            result.contentParts.push({
                type: 'text',
                textContent: currentTextSegment,
                segmentIndex: currentTextSegmentIndex,
            });
        }

        // 设置解析结果
        result.fullTextContent = fullTextContent;
        if (thinkingContent) {
            result.thinking = thinkingContent;
        }

    } catch (error) {
        console.error('解析历史消息事件失败:', error);
        // 如果解析失败，尝试将原始字符串作为文本内容返回
        result.fullTextContent = eventString;
        result.contentParts = [{
            type: 'text',
            textContent: eventString,
            segmentIndex: 1,
        }];
    }

    return result;
}
