import React, { useRef, useState } from 'react';
import { Toast, Popover } from 'antd-mobile';
import { Sender } from '@ant-design/x';
import { AddOutline } from 'antd-mobile-icons';
import { RobotOutlined, BarChartOutlined, RadarChartOutlined, BookOutlined, FileOutlined } from '@ant-design/icons';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';
import { useTheme } from '@/context/theme';

const MOCK_TOOLS = [
    { id: 'tool1', name: 'Linux 性能监控', icon: <RobotOutlined style={{ color: 'red' }} /> },
    { id: 'tool2', name: '抓包与网络分析', icon: <BarChartOutlined style={{ color: 'blue' }} /> },
    { id: 'tool3', name: '错误监控', icon: <RadarChartOutlined style={{ color: 'purple' }} /> },
    { id: 'tool4', name: '日志服务', icon: <BookOutlined style={{ color: 'orange' }} /> },
    { id: 'tool5', name: '文件同步', icon: <FileOutlined style={{ color: 'green' }} /> }
];

// 消息类型定义
export type MessageContent =
    | { type: 'text'; content: string }
    | { type: 'files'; files: File[]; fileType: 'image' | 'file'; text?: string }; // text 为可选，用于文字+文件组合

interface VoiceInputProps {
    content: string;
    setContent: (content: string) => void;
    isVoiceMode: boolean;
    onSend: (message: string | MessageContent) => void;
    onToggleVoiceMode: () => void;
    isAIRunning: boolean;
}

export const VoiceInput: React.FC<VoiceInputProps> = ({
    content,
    setContent,
    isVoiceMode,
    onSend,
    onToggleVoiceMode,
    isAIRunning,
}) => {
    const [isRecording, setIsRecording] = useState(false);
    const isRecordingRef = useRef(false);
    const [recordingCancelled, setRecordingCancelled] = useState(false);
    const longPressTimerRef = useRef<NodeJS.Timeout | null>(null);
    const touchStartYRef = useRef<number>(0);
    const isLongPressRef = useRef(false);
    const recordingStartTimeRef = useRef<number>(0);
    const senderContainerRef = useRef<HTMLDivElement>(null);
    const [showFileOptions, setShowFileOptions] = useState(false);
    const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
    const [fileType, setFileType] = useState<'image' | 'file' | null>(null); // 追踪文件类型
    const [showImageOptions, setShowImageOptions] = useState(false); // 图片选择弹窗
    const cameraInputRef = useRef<HTMLInputElement>(null);
    const photoInputRef = useRef<HTMLInputElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const { theme } = useTheme();

    const {
        recognizedText,
        setRecognizedText,
        startSpeechRecognition,
        stopSpeechRecognition,
    } = useSpeechRecognition(isLongPressRef, isRecordingRef);

    // 让输入框失焦的函数
    const blurInput = () => {
        if (senderContainerRef.current) {
            const input = senderContainerRef.current.querySelector('textarea, input');
            if (input && document.activeElement === input) {
                (input as HTMLElement).blur();
            }
        }
    };

    const handleToolClick = (toolId: string) => {
        if (isAIRunning) {
            Toast.show({
                content: 'AI 正在处理中，请稍候...',
                icon: 'loading',
                duration: 2000
            });
            return;
        }
        // 移动端触感反馈
        if (navigator.vibrate) {
            navigator.vibrate(10);
        }

        // 找到对应的工具
        const tool = MOCK_TOOLS.find(t => t.id === toolId);
        if (!tool) return;

        // 发送用户消息：执行xxx工具
        const message = `执行${tool.name}`;
        onSend(message);
    };

    const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        const files = event.target.files;
        if (files && files.length > 0) {
            const fileArray = Array.from(files);

            // 判断新选择的文件类型
            const isImage = fileArray.every(f => f.type.startsWith('image/'));
            const newFileType = isImage ? 'image' : 'file';

            // 如果已有文件，检查类型是否匹配
            if (fileType && fileType !== newFileType) {
                Toast.show({
                    content: '不支持同时添加图片和文件',
                    icon: 'fail',
                    duration: 1000
                });
                event.target.value = '';
                return;
            }

            // 检查文件大小（移动端限制：单个文件最大 10MB）
            const maxSize = 10 * 1024 * 1024; // 10MB
            const oversizedFiles = fileArray.filter(f => f.size > maxSize);

            if (oversizedFiles.length > 0) {
                Toast.show({
                    content: `部分文件超过 10MB 限制，已跳过`,
                    icon: 'fail',
                    duration: 2000
                });
            }

            const validFiles = fileArray.filter(f => f.size <= maxSize);

            if (validFiles.length > 0) {
                // 设置文件类型（首次选择时）
                if (!fileType) {
                    setFileType(newFileType);
                }

                setSelectedFiles((prev) => [...prev, ...validFiles]);

                // 打印文件信息到控制台（用于调试）
                console.log('选择的文件:', validFiles);
                validFiles.forEach(file => {
                    console.log('文件名:', file.name);
                    console.log('文件类型:', file.type);
                    console.log('文件大小:', (file.size / 1024).toFixed(2), 'KB');
                });
            }
        }

        // 重置 input，允许重复选择相同文件
        event.target.value = '';
    };

    const handleFileOptionClick = (type: 'camera' | 'photo' | 'file') => {
        // 移动端触感反馈
        if (navigator.vibrate) {
            navigator.vibrate(10);
        }

        setShowFileOptions(false);

        // 延迟触发，确保面板收起动画流畅
        setTimeout(() => {
            if (type === 'camera') {
                cameraInputRef.current?.click();
            } else if (type === 'photo') {
                photoInputRef.current?.click();
            } else if (type === 'file') {
                fileInputRef.current?.click();
            }
        }, 100);
    };

    const handleRemoveFile = (index: number) => {
        // 移动端触感反馈
        if (navigator.vibrate) {
            navigator.vibrate(10);
        }

        const newFiles = selectedFiles.filter((_, i) => i !== index);
        setSelectedFiles(newFiles);

        // 如果删除后没有文件了，重置文件类型和 Popover 状态
        if (newFiles.length === 0) {
            setFileType(null);
            setShowImageOptions(false);
        }
    };

    // 处理"添加更多"按钮点击
    const handleAddMoreFiles = () => {
        // 移动端触感反馈
        if (navigator.vibrate) {
            navigator.vibrate(10);
        }

        if (fileType === 'file') {
            // 已有文件（非图片），直接打开文件选择器
            fileInputRef.current?.click();
        } else if (fileType === 'image') {
            // 已有图片，弹出相机和相册选择
            setShowImageOptions(true);
        }
    };

    const handleVoiceTouchStart = (e: React.TouchEvent | React.MouseEvent) => {
        if (!('touches' in e)) {
            e.preventDefault();
        }

        if ('touches' in e) {
            touchStartYRef.current = e.touches[0].clientY;
        } else {
            touchStartYRef.current = e.clientY;
        }

        isLongPressRef.current = false;
        setRecordingCancelled(false);
        setRecognizedText('');

        longPressTimerRef.current = setTimeout(() => {
            isLongPressRef.current = true;
            setIsRecording(true);
            isRecordingRef.current = true;
            recordingStartTimeRef.current = Date.now();

            if (navigator.vibrate) {
                navigator.vibrate(50);
            }

            startSpeechRecognition();
        }, 300);
    };

    const handleVoiceTouchMove = (e: React.TouchEvent | React.MouseEvent) => {
        if (isRecording) {
            let currentY: number;

            if ('touches' in e) {
                currentY = e.touches[0].clientY;
            } else {
                currentY = e.clientY;
            }

            const deltaY = touchStartYRef.current - currentY;

            if (deltaY > 50) {
                setRecordingCancelled(true);
            } else {
                setRecordingCancelled(false);
            }
        }
    };

    const handleVoiceTouchEnd = () => {
        if (longPressTimerRef.current) {
            clearTimeout(longPressTimerRef.current);
            longPressTimerRef.current = null;
        }

        if (isLongPressRef.current && isRecording) {
            isLongPressRef.current = false;
            isRecordingRef.current = false;

            stopSpeechRecognition();

            const recordingDuration = Date.now() - recordingStartTimeRef.current;

            setIsRecording(false);

            if (recordingCancelled) {
                setRecognizedText('');
                setRecordingCancelled(false);
            } else {
                if (recordingDuration < 500) {
                    Toast.show({ content: '说话时间太短', icon: 'fail' });
                } else {
                    // 检查 AI 是否正在运行
                    if (isAIRunning) {
                        Toast.show({
                            content: 'AI 正在处理中，请稍候...',
                            icon: 'loading',
                            duration: 2000
                        });
                        setRecognizedText('');
                        return;
                    }

                    setTimeout(() => {
                        if (recognizedText && recognizedText.trim()) {
                            // 检查是否有导入的文件或图片
                            if (selectedFiles.length > 0 && fileType) {
                                // 语音文本 + 文件组合发送
                                onSend({
                                    type: 'files',
                                    files: selectedFiles,
                                    fileType: fileType,
                                    text: recognizedText.trim(),
                                });
                                // 清空文件状态
                                setShowImageOptions(false);
                                setSelectedFiles([]);
                                setFileType(null);
                            } else {
                                // 只发送语音识别的文本
                                onSend(recognizedText);
                            }
                            setRecognizedText('');
                        } else {
                            Toast.show({ content: '未识别到内容，请重试', icon: 'fail' });
                        }
                    }, 500);
                }
            }

            setRecordingCancelled(false);
        }
    };

    return (
        <div className="rounded-2xl pt-4 mr-2 relative bg-[var(--color-bg)]">
            {/* 隐藏的文件输入元素 - 移动端优化 */}
            {/* 相机输入：capture 属性在移动端会直接打开相机 */}
            <input
                ref={cameraInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                onChange={(e) => handleFileChange(e)}
                className="hidden"
            />
            {/* 相册输入：支持多选图片 */}
            <input
                ref={photoInputRef}
                type="file"
                accept="image/*"
                multiple
                onChange={(e) => handleFileChange(e)}
                className="hidden"
            />
            {/* 文件输入：支持选择任意类型文件 */}
            <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={(e) => handleFileChange(e)}
                className="hidden"
            />

            {/* 已选择的文件预览 - 移动端优化 */}
            {selectedFiles.length > 0 && (
                <div className="p-3">
                    <div className="flex overflow-x-auto gap-2 pb-2 scrollbar-hide">
                        {selectedFiles.map((file, index) => (
                            <div
                                key={index}
                                className="relative flex-shrink-0"
                                style={{ width: '80px' }}
                            >
                                <div className="w-full relative bg-[var(--color-background-body)] rounded-lg overflow-hidden aspect-square">
                                    {file.type.startsWith('image/') ? (
                                        <img
                                            src={URL.createObjectURL(file)}
                                            alt={file.name}
                                            className="w-full h-full object-cover"
                                        />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center p-1">
                                            <div className="text-[var(--color-text-1)] text-xs text-center line-clamp-3 overflow-hidden break-words">
                                                {file.name}
                                            </div>
                                        </div>
                                    )}
                                    <button
                                        onClick={() => handleRemoveFile(index)}
                                        className="absolute top-1 right-1 w-5 h-5 text-gray-500 text-base"
                                    >
                                        <span className="iconfont icon-delete bg-white rounded-full"></span>
                                    </button>
                                </div>
                            </div>
                        ))}
                        {/* 添加更多文件的按钮 */}
                        <div
                            className="relative flex-shrink-0"
                            style={{ width: '80px' }}
                        >
                            <Popover
                                visible={showImageOptions}
                                onVisibleChange={setShowImageOptions}
                                trigger="click"
                                stopPropagation={['click']}
                                content={
                                    <div className="flex flex-col">
                                        <button
                                            onClick={() => {
                                                setShowImageOptions(false);
                                                setTimeout(() => {
                                                    cameraInputRef.current?.click();
                                                }, 100);
                                            }}
                                            className="flex items-center gap-1 text-[var(--color-text-1)]"
                                        >
                                            <span className="iconfont icon-xiangji text-xl"></span>
                                            <span className="text-xs">相机</span>
                                        </button>
                                        <hr className="border-[var(--color-border)]" />
                                        <button
                                            onClick={() => {
                                                setShowImageOptions(false);
                                                setTimeout(() => {
                                                    photoInputRef.current?.click();
                                                }, 100);
                                            }}
                                            className="flex items-center gap-1 text-[var(--color-text-1)]">
                                            <span className="iconfont icon-tupian1 text-xl"></span>
                                            <span className="text-xs">相册</span>
                                        </button>
                                    </div>
                                }
                                placement="top"
                                mode={theme === 'dark' ? 'dark' : 'light'}
                            >
                                <button
                                    onClick={handleAddMoreFiles}
                                    className="w-full bg-[var(--color-background-body)] rounded-lg aspect-square flex items-center justify-center text-4xl text-gray-400"
                                >
                                    <AddOutline />
                                </button>
                            </Popover>
                        </div>
                    </div>
                </div>
            )}

            {/* 工具列表 */}
            <div className="mb-3 mx-2 overflow-x-auto scrollbar-hide">
                <div className="flex gap-3">
                    {MOCK_TOOLS.map((tool) => (
                        <button
                            key={tool.id}
                            onClick={() => handleToolClick(tool.id)}
                            className={'px-3 py-1 gap-1 flex items-center justify-center rounded-full border border-gray-300 '}
                            style={{
                                flexShrink: 0,
                            }}
                        >
                            {tool.icon}
                            <span className="text-xs text-[var(--color-text-2)]">{tool.name}</span>
                        </button>
                    ))}
                </div>
            </div>

            {isRecording && (
                <div className="text-center">
                    <div className={`voice-tip-top ${recordingCancelled ? 'voice-tip-cancel' : ''}`}>
                        {recordingCancelled ? '松开取消' : '松开发送,上滑取消'}
                    </div>
                </div>
            )}

            <div className="bg-[var(--color-bg)] rounded-2xl sender-container relative"
                style={{ boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)' }}>
                {isRecording && (
                    <div className="voice-record-overlay rounded-2xl">
                        <div className="wave-container rounded-2xl">
                            {Array.from({ length: 20 }).map((_, index) => (
                                <div key={index} className="wave-bar"></div>
                            ))}
                        </div>
                    </div>
                )}

                {isVoiceMode && !content.trim() ? (
                    <div className="flex items-center gap-2 p-3">
                        <div
                            className="voice-button flex-1"
                            onTouchStart={handleVoiceTouchStart}
                            onTouchMove={handleVoiceTouchMove}
                            onTouchEnd={handleVoiceTouchEnd}
                            onMouseDown={handleVoiceTouchStart}
                            onMouseMove={handleVoiceTouchMove}
                            onMouseUp={handleVoiceTouchEnd}
                            onMouseLeave={handleVoiceTouchEnd}
                        >
                            按住说话
                        </div>
                        <div className="flex items-center gap-3">
                            <span
                                className="iconfont icon-jianpan text-3xl text-[var(--color-text-1)] action-icon"
                                onMouseDown={(e) => e.preventDefault()}
                                onClick={onToggleVoiceMode}
                            ></span>
                            {selectedFiles.length > 0 ? (
                                <span
                                    className={`iconfont icon-xiangshangjiantouquan text-3xl action-icon ${isAIRunning
                                        ? 'text-gray-400 cursor-not-allowed opacity-50'
                                        : 'text-blue-600'
                                        }`}
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => {
                                        if (isAIRunning) {
                                            Toast.show({
                                                content: 'AI 正在处理中，请稍候...',
                                                icon: 'loading',
                                                duration: 2000
                                            });
                                            return;
                                        }
                                        // 发送文件（可能包含文字）
                                        if (selectedFiles.length > 0 && fileType) {
                                            onSend({
                                                type: 'files',
                                                files: selectedFiles,
                                                fileType: fileType,
                                                text: content.trim() || undefined, // 如果有输入文字，一起发送
                                            });
                                        }
                                        // 发送后清空文件、文字和重置类型
                                        setShowImageOptions(false);
                                        setSelectedFiles([]);
                                        setFileType(null);
                                        setContent(''); // 清空输入框
                                    }}
                                ></span>
                            ) : (
                                <span
                                    className="iconfont icon-a-zengjiatianjiajiahaoduo text-3xl text-[var(--color-text-1)] action-icon"
                                    style={{
                                        transform: showFileOptions ? 'rotate(45deg)' : 'rotate(0deg)',
                                        transition: 'transform 0.3s ease',
                                    }}
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => {
                                        setShowFileOptions(!showFileOptions);
                                    }}
                                ></span>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className="flex items-center gap-2" ref={senderContainerRef}>
                        <Sender
                            submitType="shiftEnter"
                            loading={false}
                            value={content}
                            onChange={setContent}
                            onSubmit={(nextContent) => {
                                if (isAIRunning) {
                                    Toast.show({
                                        content: 'AI 正在处理中，请稍候...',
                                        icon: 'loading',
                                        duration: 2000
                                    });
                                    return;
                                }
                                // 检查是否有文件，如果有则发送组合消息
                                if (selectedFiles.length > 0 && fileType) {
                                    onSend({
                                        type: 'files',
                                        files: selectedFiles,
                                        fileType: fileType,
                                        text: nextContent.trim() || undefined,
                                    });
                                    // 清空文件和输入框
                                    setShowImageOptions(false);
                                    setSelectedFiles([]);
                                    setFileType(null);
                                    setContent('');
                                } else {
                                    // 只有文字，正常发送
                                    onSend(nextContent);
                                    setContent('');
                                }
                            }}
                            placeholder={'输入消息...'}
                            style={{
                                border: 'none',
                                borderRadius: '20px',
                                backgroundColor: 'transparent',
                                width: '100%',
                            }}
                            actions={
                                content.trim() ? (
                                    <span
                                        className={`iconfont icon-xiangshangjiantouquan text-3xl action-icon ${isAIRunning
                                            ? 'text-gray-400 cursor-not-allowed opacity-50'
                                            : 'text-blue-600'
                                            }`}
                                        onClick={() => {
                                            if (isAIRunning) {
                                                Toast.show({
                                                    content: 'AI 正在处理中，请稍候...',
                                                    icon: 'loading',
                                                    duration: 2000
                                                });
                                                return;
                                            }
                                            // 优先发送文件（如果有）
                                            if (selectedFiles.length > 0 && fileType) {
                                                onSend({
                                                    type: 'files',
                                                    files: selectedFiles,
                                                    fileType: fileType,
                                                    text: content.trim() || undefined,
                                                });
                                                // 清空文件和输入框
                                                setShowImageOptions(false);
                                                setSelectedFiles([]);
                                                setFileType(null);
                                                setContent('');
                                            } else if (content.trim()) {
                                                // 只有文字，正常发送
                                                onSend(content);
                                                setContent('');
                                            }
                                        }}
                                    ></span>
                                ) : (
                                    <div className="flex items-center gap-3">
                                        <span
                                            className="iconfont icon-yuyin- text-2xl text-[var(--color-text-1)] action-icon"
                                            onMouseDown={(e) => e.preventDefault()}
                                            onClick={() => {
                                                blurInput();
                                                onToggleVoiceMode();
                                            }}
                                        ></span>
                                        {selectedFiles.length > 0 ? (
                                            <span
                                                className={`iconfont icon-xiangshangjiantouquan text-3xl action-icon ${isAIRunning
                                                    ? 'text-gray-400 cursor-not-allowed opacity-50'
                                                    : 'text-blue-600'
                                                    }`}
                                                onMouseDown={(e) => e.preventDefault()}
                                                onClick={() => {
                                                    blurInput();
                                                    if (isAIRunning) {
                                                        Toast.show({
                                                            content: 'AI 正在处理中，请稍候...',
                                                            icon: 'loading',
                                                            duration: 2000
                                                        });
                                                        return;
                                                    }
                                                    if (selectedFiles.length > 0 && fileType) {
                                                        onSend({
                                                            type: 'files',
                                                            files: selectedFiles,
                                                            fileType: fileType,
                                                            text: content.trim() || undefined,
                                                        });
                                                        // 清空文件和输入框
                                                        setShowImageOptions(false);
                                                        setSelectedFiles([]);
                                                        setFileType(null);
                                                        setContent('');
                                                    } else if (content.trim()) {
                                                        // 只有文字，正常发送
                                                        onSend(content);
                                                        setContent('');
                                                    }
                                                }}
                                            ></span>
                                        ) : <span
                                            className="iconfont icon-a-zengjiatianjiajiahaoduo text-3xl text-[var(--color-text-1)] action-icon"
                                            style={{
                                                transform: showFileOptions ? 'rotate(45deg)' : 'rotate(0deg)',
                                                transition: 'transform 0.3s ease',
                                            }}
                                            onMouseDown={(e) => e.preventDefault()}
                                            onClick={() => {
                                                blurInput();
                                                setShowFileOptions(!showFileOptions);
                                            }}
                                        ></span>}
                                    </div>
                                )
                            }
                        />
                    </div>
                )}
            </div>

            {/* 文件选项面板 - 移动端优化，带动画效果 */}
            <div
                className="overflow-hidden transition-all duration-300 ease-in-out"
                style={{
                    maxHeight: showFileOptions ? '200px' : '0',
                    opacity: showFileOptions ? 1 : 0,
                    marginTop: showFileOptions ? '12px' : '0',
                }}
            >
                <div className="my-3">
                    <div className="flex justify-around text-[var(--color-text-2)]">
                        <button
                            onClick={() => handleFileOptionClick('camera')}
                        >
                            <div className="w-22 h-22 bg-[var(--color-background-body)] rounded-xl flex flex-col items-center gap-2 justify-center">
                                <span className="iconfont icon-xiangji text-2xl"></span>
                                <span className="text-xs">相机</span>
                            </div>
                        </button>
                        <button
                            onClick={() => handleFileOptionClick('photo')}
                        >
                            <div className="w-22 h-22 bg-[var(--color-background-body)] rounded-xl flex flex-col items-center gap-2 justify-center">
                                <span className="iconfont icon-tupian1 text-2xl"></span>
                                <span className="text-xs">相册</span>
                            </div>
                        </button>
                        <button
                            onClick={() => handleFileOptionClick('file')}
                        >
                            <div className="w-22 h-22 bg-[var(--color-background-body)] rounded-xl flex flex-col items-center gap-2 justify-center">
                                <span className="iconfont icon-a-wenjianjiawenjian text-xl"></span>
                                <span className="text-xs">文件</span>
                            </div>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
