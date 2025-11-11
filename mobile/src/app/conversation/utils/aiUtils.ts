import { mockAIResponses, mockTextResponses, thinkingTemplates } from '@/constants/mockResponses';
import type { AGUIEvent } from '@/types/ag-ui';

/**
 * 模拟生成思考过程
 */
export const getThinkingProcess = (userMessage: string): string => {
    const message = userMessage.toLowerCase();

    if (message.includes('表格') || message.includes('table')) {
        return thinkingTemplates.table;
    } else if (message.includes('代码') || message.includes('code')) {
        return thinkingTemplates.code;
    } else if (message.includes('卡片') || message.includes('card')) {
        return thinkingTemplates.card;
    } else if (message.includes('列表') || message.includes('list')) {
        return thinkingTemplates.list;
    } else {
        return thinkingTemplates.default;
    }
};

/**
 * 模拟智能AI回复逻辑
 */
export const getAIReply = (userMessage: string): string | React.ReactNode => {
    const message = userMessage.toLowerCase();

    if (message.includes('表格') || message.includes('table')) {
        return mockAIResponses.table();
    } else if (message.includes('代码') || message.includes('code')) {
        return mockAIResponses.code();
    } else if (message.includes('卡片') || message.includes('card')) {
        return mockAIResponses.card();
    } else if (message.includes('列表') || message.includes('list')) {
        return mockAIResponses.list();
    } else if (message.includes('产品') || message.includes('功能')) {
        return mockTextResponses.product;
    } else if (message.includes('技术') || message.includes('支持')) {
        return mockTextResponses.support;
    } else if (message.includes('谢谢') || message.includes('感谢')) {
        return mockTextResponses.thanks;
    } else if (message.includes('帮助') || message.includes('help')) {
        return mockTextResponses.help;
    } else {
        return mockTextResponses.default[
            Math.floor(Math.random() * mockTextResponses.default.length)
        ];
    }
};

export const sleep = (ms: number = 1000) =>
    new Promise((resolve) => setTimeout(resolve, ms));

/**
 * 模拟 SSE 流式输出 - AG-UI 协议
 * 生成思考过程和 AI 回复的事件流
 */
export async function* simulateAGUIStream(
    userMessage: string,
    messageId: string
): AsyncGenerator<AGUIEvent, void, unknown> {
    const timestamp = Date.now();

    // 检测是否需要调用工具
    const needsToolCall = userMessage.toLowerCase().includes('执行工具');
    // 检测是否需要渲染申请表
    const needsApplicationForm = userMessage.includes('申请表');

    // 0. 发送 AI 运行开始事件
    yield {
        type: 'RUN_STARTED',
        timestamp,
        messageId,
    };

    // 1. 发送思考过程开始事件
    yield {
        type: 'THINKING_START',
        timestamp: Date.now(),
        messageId,
    };

    // 2. 获取思考过程文本
    const thinkingText = getThinkingProcess(userMessage);

    // 3. 分块发送思考过程内容
    const thinkingChunkSize = 10; // 每次发送 10 个字符
    for (let i = 0; i < thinkingText.length; i += thinkingChunkSize) {
        await sleep(50); // 模拟网络延迟
        const chunk = thinkingText.slice(i, i + thinkingChunkSize);
        yield {
            type: 'THINKING_CONTENT',
            timestamp: Date.now(),
            messageId,
            delta: chunk,
        };
    }

    // 4. 发送思考过程结束事件
    yield {
        type: 'THINKING_END',
        timestamp: Date.now(),
        messageId,
    };

    // 如果需要调用工具
    if (needsToolCall || needsApplicationForm) {
        await sleep(300);

        // 模拟多个工具调用
        const tools = [
            { name: 'Linux 性能监控', args: '{"server": "prod-01", "metrics": ["cpu", "memory"]}', result: 'CPU 使用率: 45%, 内存使用率: 62%, 运行正常' },
            { name: '抓包与网络分析', args: '{"interface": "eth0", "duration": 10}', result: '捕获 1234 个数据包，HTTP流量占比 78%，未发现异常连接' },
            { name: '错误监控', args: '{"service": "api-server", "level": "error"}', result: '过去24小时内检测到 3 个错误，已自动记录并分类' }
        ];

        for (let i = 0; i < tools.length; i++) {
            const tool = tools[i];
            const toolCallId = `tool-${Date.now()}-${i}`;

            // 工具调用开始
            yield {
                type: 'TOOL_CALL',
                timestamp: Date.now(),
                parentMessageId: messageId,
                toolCallId,
                toolCallName: tool.name,
            };

            await sleep(100);

            // 发送工具参数（分块）
            const argsChunkSize = 20;
            for (let j = 0; j < tool.args.length; j += argsChunkSize) {
                await sleep(30);
                const chunk = tool.args.slice(j, j + argsChunkSize);
                yield {
                    type: 'TOOL_CALL_ARGS',
                    timestamp: Date.now(),
                    toolCallId,
                    delta: chunk,
                };
            }

            // 工具参数发送完成
            yield {
                type: 'TOOL_CALL_END',
                timestamp: Date.now(),
                toolCallId,
            };

            // 模拟工具执行时间
            await sleep(800);

            // 返回工具执行结果
            yield {
                type: 'TOOL_RESULT',
                timestamp: Date.now(),
                messageId,
                toolCallId,
                result: tool.result,
            };

            await sleep(200);
        }
    }

    // 等待一小段时间再开始 AI 回复
    await sleep(200);

    // 5. 发送文本消息开始事件
    yield {
        type: 'TEXT_MESSAGE_START',
        timestamp: Date.now(),
        messageId,
        role: 'assistant',
    };

    // 6. 获取 AI 回复文本
    let aiReplyText = '';
    if (needsApplicationForm) {
        aiReplyText = '好的，申请表已经为您填入已知字段信息，点击可修改，确认后可提交申请';
    } else {
        const aiReply = getAIReply(userMessage);
        aiReplyText = typeof aiReply === 'string' ? aiReply : JSON.stringify(aiReply, null, 2);
    }

    // 7. 分块发送 AI 回复内容
    const messageChunkSize = 10; // 每次发送 10 个字符
    for (let i = 0; i < aiReplyText.length; i += messageChunkSize) {
        await sleep(40); // 模拟网络延迟
        const chunk = aiReplyText.slice(i, i + messageChunkSize);
        yield {
            type: 'TEXT_MESSAGE_CONTENT',
            timestamp: Date.now(),
            messageId,
            delta: chunk,
        };
    }

    // 8. 发送文本消息结束事件
    yield {
        type: 'TEXT_MESSAGE_END',
        timestamp: Date.now(),
        messageId,
    };

    // 如果需要渲染申请表组件
    if (needsApplicationForm) {
        await sleep(200);

        // 发送自定义事件渲染申请表
        yield {
            type: 'CUSTOM',
            name: 'render_component',
            value: {
                component: 'ApplicationForm',
                props: {
                    field: [
                        { label: '部门名称', type: 'text', name: 'department', value: '技术部', required: false, editable: false },
                        { label: '姓名', type: 'text', name: 'name', value: '张三', required: false, editable: false },
                        { label: '开始时间', type: 'datetime', name: 'start_time', value: '', required: true, editable: true },
                        { label: '结束时间', type: 'datetime', name: 'end_time', value: '', required: true, editable: true },
                        { label: '抄送人', type: 'text', name: 'Cc_person', value: ['李四', '王五', '赵六'], required: false, editable: false },
                        { label: '事由', type: 'text', name: 'reason', value: '', required: true, editable: true },
                        { label: '附件', type: 'file', name: 'attachment1', value: null, required: false, editable: true },
                    ],
                    state: 'noSubmitted'
                }
            }
        };
    }

    // 9. 发送 AI 运行结束事件
    yield {
        type: 'RUN_FINISHED',
        timestamp: Date.now(),
        messageId,
    };
}
