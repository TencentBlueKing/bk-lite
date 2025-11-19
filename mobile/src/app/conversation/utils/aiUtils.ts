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

    // K8s 巡检相关场景检测
    const isK8sInspection = userMessage.includes('k8s整体巡检') || userMessage.includes('K8s整体巡检');
    const isNode07Analysis = userMessage.includes('分析 node07');
    const isFullDiagnosis = userMessage.includes('完整诊断');
    const isHpaExecution = userMessage.includes('仅执行 HPA');
    const isLaterContinue = userMessage.includes('稍后再说');

    // x-vision 环境准备场景检测
    const isXvisionPrepare = userMessage.includes('准备 x-vision 的环境') || userMessage.includes('准备x-vision的环境');
    const isXvisionFormSubmit = userMessage.includes('表单提交') && (userMessage.includes('只读') && userMessage.includes('标准模板'));
    const isXvisionNoNeed = userMessage.includes('不需要');

    // 主动告警场景检测
    const isAlertTrigger = userMessage.includes('主动告警');
    const isAlertDetail = userMessage.includes('查看详情');
    const isAlertExecute = userMessage.includes('直接执行');

    // 运维日报场景检测
    const isDailyReport = userMessage.includes('运维日报');
    const isDailyReportSend = userMessage.includes('直接发群');

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
    } else if (isK8sInspection) {
        thinkingText = thinkingTemplates.k8sInspection;
    } else if (isNode07Analysis) {
        thinkingText = thinkingTemplates.k8sNode07Analysis;
    } else if (isFullDiagnosis) {
        thinkingText = thinkingTemplates.k8sFullDiagnosis;
    } else if (isHpaExecution) {
        thinkingText = thinkingTemplates.k8sHpaExecution;
    } else if (isLaterContinue) {
        thinkingText = thinkingTemplates.k8sLaterContinue;
    } else if (isXvisionPrepare) {
        thinkingText = thinkingTemplates.xvisionPrepare;
    } else if (isXvisionFormSubmit) {
        thinkingText = thinkingTemplates.xvisionFormSubmit;
    } else if (isXvisionNoNeed) {
        thinkingText = thinkingTemplates.xvisionNoNeed;
    } else if (isAlertTrigger) {
        thinkingText = thinkingTemplates.alertTrigger;
    } else if (isAlertDetail) {
        thinkingText = thinkingTemplates.alertDetail;
    } else if (isAlertExecute) {
        thinkingText = thinkingTemplates.alertExecute;
    } else if (isDailyReport) {
        thinkingText = thinkingTemplates.dailyReport;
    } else if (isDailyReportSend) {
        thinkingText = thinkingTemplates.dailyReportSend;
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
    if (needsToolCall || needsApplicationForm || isServerRepairFormSubmission || isK8sInspection || isNode07Analysis || isFullDiagnosis || isHpaExecution || isXvisionFormSubmit || isAlertDetail || isAlertExecute) {
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

        const k8sInspectionTools = [
            { name: 'k8s巡检任务工具', args: '{"cluster": "prod", "scope": "all"}', result: '巡检完成，共扫描 50 个节点、320 个 Pod、15 个 Service' },
            { name: '监控数据检索工具', args: '{"metrics": ["cpu", "memory", "disk"], "timeRange": "1h"}', result: '检索到 5 个异常指标，包括 node07 CPU 持续高负载' },
            { name: '日志快照扫描工具', args: '{"logLevel": "error", "timeRange": "24h"}', result: '发现 payment-service 重启 14 次，inventory-service 存储不足' },
            { name: '事件分析工具', args: '{"eventType": "Warning", "timeRange": "1h"}', result: '检测到 3 个 PVC 使用率超过 85%，Ingress 响应延迟偶现' }
        ];

        const k8sNode07Tools = [
            { name: '监控指标分析工具', args: '{"node": "node07", "metrics": ["cpu", "memory", "io"]}', result: 'node07 CPU 92%，主要负载来自 image-service' },
            { name: 'Pod资源分析工具', args: '{"node": "node07"}', result: 'image-service 占用 CPU 75%，其他 Pod 正常' }
        ];

        const k8sFullDiagnosisTools = [
            { name: '服务诊断工具', args: '{"service": "image-service"}', result: '最近 20 分钟新建 310 个 resize 任务，负载激增' },
            { name: '日志分析工具', args: '{"service": "image-service", "timeRange": "30m"}', result: '频繁出现 CPU Throttling 警告' },
            { name: '事件分析工具', args: '{"service": "image-service"}', result: '未配置 HPA，无法自动扩容' },
            { name: '异常检测工具', args: '{"service": "image-service"}', result: 'CPU limit 仅 300m，建议调整到 800m' }
        ];

        const k8sHpaTools = [
            { name: 'Node自动化操作工具', args: '{"action": "apply-hpa", "service": "image-service", "cpu": 60, "replicas": "3-10"}', result: 'HPA 配置成功，当前副本数已扩容到 10，node07 CPU 降至 61%' }
        ];

        const xvisionK8sTools = [
            { name: 'K8s资源操作工具', args: '{"action": "create-namespace", "name": "x-vision-pre", "quota": {"cpu": "16", "memory": "32Gi"}, "role": "readonly"}', result: 'Namespace x-vision-pre 创建成功，ResourceQuota 已应用，只读角色已绑定到开发组' }
        ];

        const alertDetailTools = [
            { name: '监控指标查询工具', args: '{"service": "order-service", "metrics": ["response_time", "queue_length"]}', result: '查询完成：平均响应时间 2.1s，Redis 队列长度 150' },
            { name: '自动化分析工具', args: '{"service": "order-service", "analysis_type": "performance"}', result: '分析完成：发现 order-service-pod-3/4/5 受影响，Redis 连接池共享导致延迟' }
        ];

        const alertExecuteTools = [
            { name: 'K8s自动化操作工具', args: '{"action": "isolate-redis-pool", "service": "order-service"}', result: 'Redis 连接池隔离成功' },
            { name: '监控指标查询工具', args: '{"service": "order-service", "metrics": ["response_time", "queue_length"]}', result: '验证完成：响应时间降至 0.8s，队列长度降至 30' },
            { name: '日志记录工具', args: '{"action": "log-optimization", "service": "order-service"}', result: '优化操作已记录到系统日志' }
        ];

        // 根据用户消息筛选要执行的工具
        let tools = allTools;
        if (needsApplicationForm || isServerRepairFormSubmission) {
            tools = formTools;
        } else if (isSubmitWorkOrder) {
            tools = wordOrderTools;
        } else if (isK8sInspection) {
            tools = k8sInspectionTools;
        } else if (isNode07Analysis) {
            tools = k8sNode07Tools;
        } else if (isFullDiagnosis) {
            tools = k8sFullDiagnosisTools;
        } else if (isHpaExecution) {
            tools = k8sHpaTools;
        } else if (isXvisionFormSubmit) {
            tools = xvisionK8sTools;
        } else if (isAlertDetail) {
            tools = alertDetailTools;
        } else if (isAlertExecute) {
            tools = alertExecuteTools;
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
    } else if (isK8sInspection) {
        aiReplyText = mockTextResponses.k8sInspection;
    } else if (isNode07Analysis) {
        aiReplyText = mockTextResponses.k8sNode07Analysis;
    } else if (isFullDiagnosis) {
        aiReplyText = mockTextResponses.k8sFullDiagnosis;
    } else if (isHpaExecution) {
        aiReplyText = mockTextResponses.k8sHpaExecution;
    } else if (isLaterContinue) {
        aiReplyText = mockTextResponses.k8sLaterContinue;
    } else if (isXvisionPrepare) {
        aiReplyText = mockTextResponses.xvisionPrepare;
    } else if (isXvisionFormSubmit) {
        aiReplyText = mockTextResponses.xvisionFormSubmit;
    } else if (isXvisionNoNeed) {
        aiReplyText = mockTextResponses.xvisionNoNeed;
    } else if (isAlertTrigger) {
        aiReplyText = mockTextResponses.alertTrigger;
    } else if (isAlertDetail) {
        aiReplyText = mockTextResponses.alertDetailText;
    } else if (isAlertExecute) {
        aiReplyText = mockTextResponses.alertExecuteText;
    } else if (isDailyReport) {
        aiReplyText = mockTextResponses.dailyReport;
    } else if (isDailyReportSend) {
        aiReplyText = mockTextResponses.dailyReportSend;
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

    // 如果需要渲染申请表组件或 K8s 巡检按钮组
    if (needsApplicationForm || isServerRepair || isServerRepairFormSubmission || isK8sInspection || isNode07Analysis || isFullDiagnosis || isHpaExecution || isXvisionPrepare || isXvisionFormSubmit || isAlertTrigger || isAlertDetail || isAlertExecute || isDailyReport) {
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
        } else if (isK8sInspection) {
            // K8s 巡检完成,显示问题选择按钮
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'SelectionButtons',
                    props: {
                        buttons: [
                            { id: 'node07', text: '分析 node07', message: '分析 node07' },
                            { id: 'payment', text: '查看 payment-service', message: '查看 payment-service' },
                            { id: 'pending', text: '看 Pending Pod', message: '看 Pending Pod' },
                            { id: 'pvc', text: '看 PVC', message: '看 PVC' },
                            { id: 'ingress', text: '看 Ingress', message: '看 Ingress' },
                        ],
                        layout: 'vertical'
                    }
                }
            };
        } else if (isNode07Analysis) {
            // node07 分析完成,显示下一步操作按钮
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'SelectionButtons',
                    props: {
                        buttons: [
                            { id: 'diagnosis', text: '完整诊断', message: '完整诊断' },
                            { id: 'scale', text: '直接扩容', message: '直接扩容' },
                            { id: 'ignore', text: '忽略', message: '忽略' },
                        ],
                        layout: 'vertical'
                    }
                }
            };
        } else if (isFullDiagnosis) {
            // 完整诊断完成,显示方案选择按钮
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'SelectionButtons',
                    props: {
                        buttons: [
                            { id: 'hpa', text: '仅执行 HPA', message: '仅执行 HPA' },
                            { id: 'limit', text: '仅调整 limit', message: '仅调整 limit' },
                            { id: 'both', text: 'HPA + limit', message: 'HPA + limit' },
                            { id: 'skip', text: '不处理', message: '不处理' },
                        ],
                        layout: 'vertical'
                    }
                }
            };
        } else if (isHpaExecution) {
            // HPA 执行完成,显示是否继续按钮
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'SelectionButtons',
                    props: {
                        buttons: [
                            { id: 'continue', text: '继续处理', message: '继续处理' },
                            { id: 'later', text: '稍后再说', message: '稍后再说' },
                        ],
                        layout: 'horizontal'
                    }
                }
            };
        } else if (isXvisionPrepare) {
            // x-vision 环境准备,显示配置表单(使用单选按钮组)
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'ApplicationForm',
                    props: {
                        field: [
                            {
                                label: '请确认环境类型和权限要求',
                                type: 'radio',
                                name: 'env_type',
                                value: null,
                                options: [
                                    { label: '测试', value: 'test' },
                                    { label: '预发', value: 'pre' },
                                    { label: '生产', value: 'prod' }
                                ],
                                required: true,
                                editable: true
                            },
                            {
                                label: '资源配额使用标准模板还是自定义？',
                                type: 'radio',
                                name: 'quota_type',
                                value: null,
                                options: [
                                    { label: '标准模板', value: 'standard' },
                                    { label: '自定义', value: 'custom' }
                                ],
                                required: true,
                                editable: true
                            },
                            {
                                label: '开发权限是',
                                type: 'radio',
                                name: 'permission',
                                value: null,
                                options: [
                                    { label: '只读', value: 'readonly' },
                                    { label: '读写', value: 'readwrite' },
                                    { label: '管理员', value: 'admin' }
                                ],
                                required: true,
                                editable: true
                            },
                        ],
                        state: 'noSubmitted'
                    }
                }
            };
        } else if (isXvisionFormSubmit) {
            // x-vision 环境创建完成,显示信息卡片
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'InformationCard',
                    props: {
                        content: [
                            { type: 'paragraph', content: 'Namespace: x-vision-pre' },
                            { type: 'paragraph', content: 'ResourceQuota: CPU 16 / Mem 32Gi' },
                            { type: 'paragraph', content: '权限: 只读角色 + 绑定开发组' },
                        ]
                    }
                }
            };
        } else if (isAlertTrigger) {
            // 主动告警，显示操作按钮
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'SelectionButtons',
                    props: {
                        buttons: [
                            { id: 'isolate', text: '立即隔离', message: '立即隔离 Redis 连接池' },
                            { id: 'detail', text: '查看详情', message: '查看详情' },
                            { id: 'ignore', text: '忽略', message: '忽略告警' },
                        ],
                        layout: 'horizontal'
                    }
                }
            };
        } else if (isAlertDetail) {
            // 查看详情后，显示信息卡片
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'InformationCard',
                    props: {
                        content: [
                            { type: 'paragraph', content: 'order-service 平均响应时间：2.1s（正常 <1s）' },
                            { type: 'paragraph', content: 'Redis 队列长度：当前 150（阈值 50）' },
                            { type: 'paragraph', content: '涉及实例：order-service-pod-3/4/5' },
                        ]
                    }
                }
            };
        } else if (isAlertExecute) {
            // 执行完成后，显示结果卡片
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'InformationCard',
                    props: {
                        content: [
                            { type: 'paragraph', content: 'Redis 排队长度：30（已恢复正常）' },
                            { type: 'paragraph', content: 'order-service 平均响应时间：0.8s（正常 <1s）' },
                            { type: 'paragraph', content: '相关 Pod：order-service-pod-3/4/5' },
                        ]
                    }
                }
            };
        } else if (isDailyReport) {
            // 运维日报，显示操作按钮
            yield {
                type: 'CUSTOM',
                name: 'render_component',
                value: {
                    component: 'SelectionButtons',
                    props: {
                        buttons: [
                            { id: 'export', text: '直接导出pdf', message: '直接导出pdf' },
                            { id: 'send', text: '直接发群', message: '直接发群' },
                        ],
                        layout: 'horizontal'
                    }
                }
            };
        }
    }

    // x-vision 卡片后需要再显示文本 + 按钮组
    if (isXvisionFormSubmit) {
        await sleep(200);

        // 发送文本消息开始事件
        yield {
            type: 'TEXT_MESSAGE_START',
            timestamp: Date.now(),
            messageId,
            role: 'assistant',
        };

        // 发送第二段文本
        const secondText = mockTextResponses.xvisionAfterCard;
        const secondChunkSize = 10;
        for (let i = 0; i < secondText.length; i += secondChunkSize) {
            await sleep(40);
            const chunk = secondText.slice(i, i + secondChunkSize);
            yield {
                type: 'TEXT_MESSAGE_CONTENT',
                timestamp: Date.now(),
                messageId,
                delta: chunk,
            };
        }

        // 发送文本消息结束事件
        yield {
            type: 'TEXT_MESSAGE_END',
            timestamp: Date.now(),
            messageId,
        };

        await sleep(200);

        // 渲染部署选择按钮
        yield {
            type: 'CUSTOM',
            name: 'render_component',
            value: {
                component: 'SelectionButtons',
                props: {
                    buttons: [
                        { id: 'need', text: '需要', message: '需要部署 Helm' },
                        { id: 'no_need', text: '不需要', message: '不需要' },
                    ],
                    layout: 'horizontal'
                }
            }
        };
    }

    // 告警详情场景：卡片后显示建议文本 + 操作按钮
    if (isAlertDetail) {
        await sleep(200);

        // 发送建议文本
        yield {
            type: 'TEXT_MESSAGE_START',
            timestamp: Date.now(),
            messageId,
            role: 'assistant',
        };

        const suggestionText = mockTextResponses.alertDetailSuggestion;
        const suggestionChunkSize = 10;
        for (let i = 0; i < suggestionText.length; i += suggestionChunkSize) {
            await sleep(40);
            const chunk = suggestionText.slice(i, i + suggestionChunkSize);
            yield {
                type: 'TEXT_MESSAGE_CONTENT',
                timestamp: Date.now(),
                messageId,
                delta: chunk,
            };
        }

        yield {
            type: 'TEXT_MESSAGE_END',
            timestamp: Date.now(),
            messageId,
        };

        await sleep(200);

        // 渲染操作选择按钮
        yield {
            type: 'CUSTOM',
            name: 'render_component',
            value: {
                component: 'SelectionButtons',
                props: {
                    buttons: [
                        { id: 'execute', text: '直接执行', message: '直接执行' },
                        { id: 'script', text: '生成脚本', message: '生成脚本' },
                    ],
                    layout: 'horizontal'
                }
            }
        };
    }

    // 告警执行场景：卡片后显示监控文本
    if (isAlertExecute) {
        await sleep(200);

        // 发送监控继续文本
        yield {
            type: 'TEXT_MESSAGE_START',
            timestamp: Date.now(),
            messageId,
            role: 'assistant',
        };

        const endText = mockTextResponses.alertExecuteEnd;
        const endChunkSize = 10;
        for (let i = 0; i < endText.length; i += endChunkSize) {
            await sleep(40);
            const chunk = endText.slice(i, i + endChunkSize);
            yield {
                type: 'TEXT_MESSAGE_CONTENT',
                timestamp: Date.now(),
                messageId,
                delta: chunk,
            };
        }

        yield {
            type: 'TEXT_MESSAGE_END',
            timestamp: Date.now(),
            messageId,
        };
    }

    // 发送 AI 运行结束事件
    yield {
        type: 'RUN_FINISHED',
        timestamp: Date.now(),
        messageId,
    };
}
