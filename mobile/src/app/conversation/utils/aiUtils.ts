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

    // 检测是否需要调用工具 - 支持具体工具名称
    const needsToolCall = userMessage.includes('执行') && (
        userMessage.includes('工具') ||
        userMessage.includes('Linux 性能监控') ||
        userMessage.includes('抓包与网络分析') ||
        userMessage.includes('错误监控') ||
        userMessage.includes('日志服务') ||
        userMessage.includes('文件同步')
    );
    // 检测是否需要渲染申请表
    const needsApplicationForm = userMessage.includes('申请表');
    const isServerRepair = userMessage.includes('服务器连接超时');
    const isServerRepairFormSubmission = userMessage.includes('表单提交') && userMessage.includes('故障开始时间');
    const isSubmitWorkOrder = userMessage.includes('确认提交工单');
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
    let thinkingText = '';
    if (isServerRepair) {
        thinkingText = thinkingTemplates.serverRepair;
    } else if (isServerRepairFormSubmission) {
        thinkingText = thinkingTemplates.serverRepairFormSubmission;
    } else if (isSubmitWorkOrder) {
        thinkingText = thinkingTemplates.submitWorkOrder;
    } else {
        thinkingText = getThinkingProcess(userMessage);
    }
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
    if (needsToolCall || needsApplicationForm || isServerRepairFormSubmission) {
        await sleep(300);

        // 根据用户消息确定要执行的工具
        const allTools = [
            { name: 'Linux 性能监控', args: '{"server": "prod-01", "metrics": ["cpu", "memory"]}', result: 'CPU 使用率: 45%, 内存使用率: 62%, 运行正常' },
            { name: '抓包与网络分析', args: '{"interface": "eth0", "duration": 10}', result: '捕获 1234 个数据包，HTTP流量占比 78%，未发现异常连接' },
            { name: '错误监控', args: '{"service": "api-server", "level": "error"}', result: '过去24小时内检测到 3 个错误，已自动记录并分类' },
            { name: '日志服务', args: '{"source": "application", "level": "info"}', result: '已收集最近100条日志，未发现异常' },
            { name: '文件同步', args: '{"source": "/data", "target": "/backup"}', result: '同步完成，共传输文件 256 个，总大小 1.2GB' }
        ];

        const formTools = [
            { name: 'ITSM 事件分类工具', args: '', result: '自动识别事件归属。' },
            { name: '知识库检索引擎', args: '', result: '按关键词精准定位相关文档（故障排查步骤、审批流程），避免重复分析。' },
            { name: '信息校验工具', args: '', result: '列出必填信息清单，确保工单字段完整，减少后续返工。' },
            { name: '工单生成模板工具', args: '', result: '标准化工单结构，自动生成唯一编号，关联对应处置团队（如运维组）。' },
            { name: '工单流转工具', args: '', result: '推送工单至负责人企业微信 / 邮箱，同步更新 ITSM 系统工单状态（“待处理”）。' },
            { name: '进度跟踪工具', args: '', result: '对接 ITSM 系统状态接口，自动抓取更新，触发进度通知（短信 / 系统消息）。' }
        ];

        const wordOrderTools = [
            { name: '进度跟踪工具', args: '', result: '对接 ITSM 系统状态接口，自动抓取更新，触发进度通知（短信 / 系统消息）。' },
            { name: '报告生成工具', args: '', result: '自动整理工单全流程数据，生成可导出的总结文档，支持后续复盘。' }
        ];

        // 根据用户消息筛选要执行的工具
        let tools = allTools;
        if (needsApplicationForm || isServerRepairFormSubmission) {
            tools = formTools;
        } else if (isSubmitWorkOrder) {
            tools = wordOrderTools;
        } else if (userMessage.includes('Linux 性能监控')) {
            tools = allTools.filter(t => t.name === 'Linux 性能监控');
        } else if (userMessage.includes('抓包与网络分析')) {
            tools = allTools.filter(t => t.name === '抓包与网络分析');
        } else if (userMessage.includes('错误监控')) {
            tools = allTools.filter(t => t.name === '错误监控');
        } else if (userMessage.includes('日志服务')) {
            tools = allTools.filter(t => t.name === '日志服务');
        } else if (userMessage.includes('文件同步')) {
            tools = allTools.filter(t => t.name === '文件同步');
        }

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
        aiReplyText = '好的，申请表已经为您填入已知字段信息，点击可修改，确认后可提交申请。';
    } else if (isServerRepair) {
        aiReplyText = mockTextResponses.serverRepair;
    } else if (isServerRepairFormSubmission) {
        aiReplyText = mockTextResponses.serverRepairFormSubmission;
    } else if (isSubmitWorkOrder) {
        aiReplyText = mockTextResponses.submitWorkOrder;
    } else if (needsToolCall) {
        // 根据执行的工具生成对应的回复
        if (userMessage.includes('Linux 性能监控')) {
            aiReplyText = '已完成 Linux 性能监控，服务器 prod-01 运行状态良好，CPU 和内存使用率均在正常范围内。';
        } else if (userMessage.includes('抓包与网络分析')) {
            aiReplyText = '网络抓包分析完成，HTTP 流量占主导地位，网络连接正常，未检测到异常流量。';
        } else if (userMessage.includes('错误监控')) {
            aiReplyText = '错误监控检查完成，过去 24 小时内发现少量错误，均已记录并分类，建议关注错误趋势。';
        } else if (userMessage.includes('日志服务')) {
            aiReplyText = '日志服务查询完成，最近的应用日志显示系统运行正常，未发现异常记录。';
        } else if (userMessage.includes('文件同步')) {
            aiReplyText = '文件同步任务已完成，所有文件已成功从源目录传输到备份目录。';
        } else {
            aiReplyText = '工具执行完成，请查看上方的执行结果详情。';
        }
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
    if (needsApplicationForm || isServerRepair || isServerRepairFormSubmission) {
        await sleep(200);

        // 发送自定义事件渲染申请表
        if (needsApplicationForm) {
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
        } else if (isServerRepair) {
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'ApplicationForm',
                    props: {
                        field: [
                            { label: '故障开始时间', type: 'datetime', name: 'start_time', value: '', required: true, editable: true },
                            { label: '是否测试过清除浏览器缓存', type: 'radio', name: 'cleared_cache', value: null, options: [{ label: '是', value: true }, { label: '否', value: false }], required: true, editable: true },
                        ],
                        state: 'noSubmitted'
                    }
                }
            };
        } else if (isServerRepairFormSubmission) {
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'InformationCard',
                    props: {
                        content: [
                            { type: 'text', content: '📋 工单信息' },
                            { type: 'divider' },
                            { type: 'paragraph', content: '工单编号: EVT-20240520-001' },
                            { type: 'paragraph', content: '事件类型: 系统可用性故障（高优先级）' },
                            { type: 'paragraph', content: '影响范围: 全公司（约 200 人）' },
                            { type: 'divider' },
                            { type: 'text', content: '🔍 故障详情' },
                            { type: 'paragraph', content: '办公系统登录超时，清除缓存后问题未解决，故障持续 10 分钟。' },
                            { type: 'divider' },
                            { type: 'text', content: '⚙️ 处置预案' },
                            {
                                type: 'list',
                                items: [
                                    '优先检查应用服务器状态及网络连通性',
                                    '同步联系运维团队紧急排查',
                                    '记录故障时间线及恢复过程',
                                    '完成后提交故障分析报告'
                                ]
                            },
                            { type: 'button', text: '确认提交工单', message: '确认提交工单' },
                        ]
                    }
                }
            };
        }
    }

    // 发送 AI 运行结束事件
    yield {
        type: 'RUN_FINISHED',
        timestamp: Date.now(),
        messageId,
    };
}
