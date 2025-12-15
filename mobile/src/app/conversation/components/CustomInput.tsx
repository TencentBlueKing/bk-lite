import React, { useRef, useState } from 'react';
import { Toast, Popover, ImageViewer } from 'antd-mobile';
import { Sender } from '@ant-design/x';
import { AddOutline, ExclamationCircleFill } from 'antd-mobile-icons';
import { RobotOutlined, BarChartOutlined, RadarChartOutlined, BookOutlined, FileOutlined, FileExcelFilled, FileMarkdownFilled, FilePdfFilled, FilePptFilled, FileTextFilled, FileUnknownFilled, FileWordFilled, FileZipFilled } from '@ant-design/icons';
import { useTheme } from '@/context/theme';
import { VoiceRecorder } from './VoiceRecorder';
import { useTranslation } from '@/utils/i18n';

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
    | { type: 'files'; files: File[]; fileType: 'image' | 'file'; text?: string; base64Data: string[] }; // text 为可选，base64Data 存储转换后的数据

interface CustomInputProps {
    content: string;
    setContent: (content: string) => void;
    isVoiceMode: boolean;
    onSend: (message: string | MessageContent) => void;
    onToggleVoiceMode: () => void;
    isAIRunning: boolean;
}

export const CustomInput: React.FC<CustomInputProps> = ({
    content,
    setContent,
    isVoiceMode,
    onSend,
    onToggleVoiceMode,
    isAIRunning,
}) => {
    const { t } = useTranslation();
    const [isRecording, setIsRecording] = useState(false);
    const [recordingCancelled, setRecordingCancelled] = useState(false);
    const senderContainerRef = useRef<HTMLDivElement>(null);
    const [showFileOptions, setShowFileOptions] = useState(false);
    const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
    const [fileType, setFileType] = useState<'image' | 'file' | null>(null); // 追踪文件类型
    const [showImageOptions, setShowImageOptions] = useState(false); // 图片选择弹窗
    const cameraInputRef = useRef<HTMLInputElement>(null);
    const photoInputRef = useRef<HTMLInputElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const { theme } = useTheme();
    const [fileConversionStatus, setFileConversionStatus] = useState<Record<number, boolean | 'error'>>({}); // 记录每个文件转换状态：true=完成, false=转换中, 'error'=失败
    const [fileBase64Data, setFileBase64Data] = useState<Record<number, string>>({}); // 存储每个文件的base64数据
    const [imageViewerVisible, setImageViewerVisible] = useState(false);
    const [currentPreviewImage, setCurrentPreviewImage] = useState<string>('');

    // 处理图片点击预览
    const handleImagePreview = (file: File, e: React.MouseEvent) => {
        e.stopPropagation();
        const imageUrl = URL.createObjectURL(file);
        setCurrentPreviewImage(imageUrl);
        setImageViewerVisible(true);
    };

    // 获取文件扩展名
    const getFileExtension = (fileName: string): string => {
        const ext = fileName.split('.').pop()?.toUpperCase();
        return ext || 'FILE';
    };

    // 获取文件名（不包含扩展名）
    const getFileNameWithoutExtension = (fileName: string): string => {
        const lastDotIndex = fileName.lastIndexOf('.');
        if (lastDotIndex === -1) return fileName;
        return fileName.substring(0, lastDotIndex);
    };

    // 格式化文件大小
    const formatFileSize = (bytes: number): string => {
        const mb = bytes / (1024 * 1024);
        if (mb >= 1) {
            return `${mb.toFixed(2)} MB`;
        }
        const kb = bytes / 1024;
        return `${kb.toFixed(2)} KB`;
    };

    // 根据文件类型获取图标和颜色
    const getFileIcon = (fileName: string) => {
        const ext = fileName.split('.').pop()?.toLowerCase() || '';

        // Excel 文件
        if (['xls', 'xlsx', 'xlsm', 'xlsb', 'csv'].includes(ext)) {
            return { icon: <FileExcelFilled />, color: '#107C41' };
        }
        // Word 文件
        if (['doc', 'docx', 'docm', 'dot', 'dotx'].includes(ext)) {
            return { icon: <FileWordFilled />, color: '#2B579A' };
        }
        // PowerPoint 文件
        if (['ppt', 'pptx', 'pptm', 'pps', 'ppsx'].includes(ext)) {
            return { icon: <FilePptFilled />, color: '#D24726' };
        }
        // PDF 文件
        if (ext === 'pdf') {
            return { icon: <FilePdfFilled />, color: '#F40F02' };
        }
        // 压缩文件
        if (['zip', 'rar', '7z', 'tar', 'gz', 'bz2'].includes(ext)) {
            return { icon: <FileZipFilled />, color: '#FFA500' };
        }
        // Markdown 文件
        if (['md', 'markdown'].includes(ext)) {
            return { icon: <FileMarkdownFilled />, color: '#000000' };
        }
        // 文本文件
        if (['txt', 'log', 'json', 'xml', 'yml', 'yaml', 'ini', 'conf', 'cfg'].includes(ext)) {
            return { icon: <FileTextFilled />, color: '#666666' };
        }
        // 默认未知文件
        return { icon: <FileUnknownFilled />, color: '#999999' };
    };

    // 验证文件转换状态
    const validateFileConversion = (): boolean => {
        if (selectedFiles.length === 0) return true;

        // 检查是否有转换失败的文件
        const hasError = selectedFiles.some((_, index) => fileConversionStatus[index] === 'error');
        if (hasError) {
            Toast.show({
                content: t('chat.fileConversionError'),
                icon: 'fail',
                duration: 2000
            });
            return false;
        }

        // 检查是否所有文件都已转换完成
        const allConverted = selectedFiles.every((_, index) => fileConversionStatus[index] === true);
        if (!allConverted) {
            Toast.show({
                content: t('chat.uploading'),
                icon: 'loading',
                duration: 2000
            });
            return false;
        }

        return true;
    };

    // 清空文件相关状态
    const clearFileStates = () => {
        setShowImageOptions(false);
        setSelectedFiles([]);
        setFileType(null);
        setFileConversionStatus({});
        setFileBase64Data({});
    };

    // 处理语音识别发送
    const handleVoiceSend = (text: string) => {
        // 检查文件转换状态
        if (selectedFiles.length > 0 && fileType) {
            if (!validateFileConversion()) return;

            // 收集所有文件的base64数据
            const base64Array = selectedFiles.map((_, index) => fileBase64Data[index]);

            // 语音文本 + 文件组合发送
            onSend({
                type: 'files',
                files: selectedFiles,
                fileType: fileType,
                text: text,
                base64Data: base64Array,
            });
            clearFileStates();
        } else {
            // 只发送语音识别的文本
            onSend(text);
        }
    };

    // 将文件转换为base64
    const convertFileToBase64 = (file: File, index: number): Promise<string> => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const base64String = reader.result as string;
                setFileBase64Data(prev => ({ ...prev, [index]: base64String }));
                setFileConversionStatus(prev => ({ ...prev, [index]: true }));
                resolve(base64String);
            };
            reader.onerror = () => {
                // 使用特殊值 'error' 表示转换失败
                setFileConversionStatus(prev => ({ ...prev, [index]: 'error' as any }));
                reject(reader.error);
            };
            reader.readAsDataURL(file);
        });
    };

    // 重试转换失败的文件
    const retryConversion = async (file: File, index: number) => {
        setFileConversionStatus(prev => ({ ...prev, [index]: false }));
        try {
            await convertFileToBase64(file, index);
        } catch (error) {
            console.error('File conversion failed.:', file.name, error);
            Toast.show({
                content: t('chat.fileConversionFailed'),
                icon: 'fail',
                duration: 2000
            });
        }
    };

    // 让输入框失焦的函数
    const blurInput = () => {
        if (senderContainerRef.current) {
            const input = senderContainerRef.current.querySelector('textarea, input');
            if (input && document.activeElement === input) {
                (input as HTMLElement).blur();
            }
        }
    };

    // 统一的发送处理函数
    const handleSendWithFiles = (text?: string) => {
        if (isAIRunning) {
            Toast.show({
                content: t('chat.aiProcessing'),
                icon: 'loading',
                duration: 2000
            });
            return;
        }

        // 优先发送文件（如果有）
        if (selectedFiles.length > 0 && fileType) {
            if (!validateFileConversion()) return;

            // 收集所有文件的base64数据
            const base64Array = selectedFiles.map((_, index) => fileBase64Data[index]);

            onSend({
                type: 'files',
                files: selectedFiles,
                fileType: fileType,
                text: text?.trim() || undefined,
                base64Data: base64Array,
            });
            // 清空文件和输入框
            clearFileStates();
            setContent('');
        } else if (text?.trim()) {
            // 只有文字，正常发送
            onSend(text);
            setContent('');
        }
    };

    const handleToolClick = (toolId: string) => {
        if (isAIRunning) {
            Toast.show({
                content: t('chat.aiProcessing'),
                icon: 'loading',
                duration: 2000
            });
            return;
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

            // 检查总数是否超过9个
            if (selectedFiles.length + fileArray.length > 9) {
                Toast.show({
                    content: t('chat.fileCountLimit') || '最多只能添加9个文件',
                    icon: 'fail',
                    duration: 2000
                });
                event.target.value = '';
                return;
            }

            // 判断新选择的文件类型
            const isImage = fileArray.every(f => f.type.startsWith('image/'));
            const newFileType = isImage ? 'image' : 'file';

            // 如果已有文件，检查类型是否匹配
            if (fileType && fileType !== newFileType) {
                Toast.show({
                    content: t('chat.addLimit'),
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
                    content: t('chat.fileSizeLimitExceeded'),
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

                const currentLength = selectedFiles.length;
                setSelectedFiles((prev) => [...prev, ...validFiles]);

                // 开始转换新添加的文件为base64
                validFiles.forEach(async (file, idx) => {
                    const fileIndex = currentLength + idx;
                    // 初始化转换状态为false（转换中）
                    setFileConversionStatus(prev => ({ ...prev, [fileIndex]: false }));

                    try {
                        // 异步转换文件
                        await convertFileToBase64(file, fileIndex);
                        console.log(`文件 ${file.name} 转换完成`);
                    } catch (error) {
                        console.error('File conversion failed.:', file.name, error);
                        Toast.show({
                            content: t('chat.fileConversionFailed'),
                            icon: 'fail',
                            duration: 2000
                        });
                    }
                });
            }
        }

        // 重置 input，允许重复选择相同文件
        event.target.value = '';
    };

    const handleFileOptionClick = (type: 'camera' | 'photo' | 'file') => {
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
        const newFiles = selectedFiles.filter((_, i) => i !== index);
        setSelectedFiles(newFiles);

        // 清理对应的转换状态和base64数据
        const newConversionStatus: Record<number, boolean | 'error'> = {};
        const newBase64Data: Record<number, string> = {};
        newFiles.forEach((_, newIndex) => {
            const oldIndex = newIndex >= index ? newIndex + 1 : newIndex;
            newConversionStatus[newIndex] = fileConversionStatus[oldIndex];
            if (fileBase64Data[oldIndex]) {
                newBase64Data[newIndex] = fileBase64Data[oldIndex];
            }
        });
        setFileConversionStatus(newConversionStatus);
        setFileBase64Data(newBase64Data);

        // 如果删除后没有文件了，重置文件类型和 Popover 状态
        if (newFiles.length === 0) {
            setFileType(null);
            setShowImageOptions(false);
        }
    };

    // 处理"添加更多"按钮点击
    const handleAddMoreFiles = () => {
        if (fileType === 'file') {
            // 已有文件（非图片），直接打开文件选择器
            fileInputRef.current?.click();
        } else if (fileType === 'image') {
            // 已有图片，弹出相机和相册选择
            setShowImageOptions(true);
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
                                style={{
                                    width: file.type.startsWith('image/') ? '80px' : '200px',
                                    height: '80px'
                                }}
                            >
                                <div className="w-full h-full relative border border-[var(--color-border)] rounded-lg overflow-hidden">
                                    {file.type.startsWith('image/') ? (
                                        <img
                                            src={URL.createObjectURL(file)}
                                            alt={file.name}
                                            className="w-full h-full object-cover cursor-pointer"
                                            onClick={(e) => handleImagePreview(file, e)}
                                        />
                                    ) : (
                                        <div className="w-full h-full flex items-center gap-2 p-2">
                                            {(() => {
                                                const { icon, color } = getFileIcon(file.name);
                                                return (
                                                    <div
                                                        className="flex-shrink-0 w-10 h-10 rounded flex items-center justify-center text-4xl"
                                                        style={{ color: color }}
                                                    >
                                                        {icon}
                                                    </div>
                                                );
                                            })()}
                                            <div className="flex-1 min-w-0 h-full flex flex-col justify-between py-0.5">
                                                <div className="flex-1 flex items-center min-h-0">
                                                    <div className="text-[var(--color-text-1)] text-xs font-medium line-clamp-2 break-all overflow-hidden">
                                                        {getFileNameWithoutExtension(file.name)}
                                                    </div>
                                                </div>
                                                <div className="text-[var(--color-text-3)] text-xs flex-shrink-0">
                                                    {getFileExtension(file.name)} | {formatFileSize(file.size)}
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                    {/* Loading遮罩 - 转换中 */}
                                    {fileConversionStatus[index] === false && (
                                        <div
                                            className="absolute inset-0 flex items-center justify-center rounded-lg"
                                            style={{ backgroundColor: 'rgba(0, 0, 0, 0.4)' }}
                                        >
                                            <div className="animate-spin rounded-full h-6 w-6 border-2 border-white border-t-transparent"></div>
                                        </div>
                                    )}
                                    {/* 错误遮罩 - 转换失败 */}
                                    {fileConversionStatus[index] === 'error' && (
                                        <div
                                            className="absolute inset-0 flex flex-col items-center justify-center gap-1 rounded-lg"
                                            style={{ backgroundColor: 'rgba(0, 0, 0, 0.8)' }}
                                        >
                                            <ExclamationCircleFill className="text-red-500 text-2xl" />
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    retryConversion(file, index);
                                                }}
                                                className="text-white text-xs bg-black bg-opacity-50 px-2 py-1 rounded"
                                            >
                                                {t('common.retry')}
                                            </button>
                                        </div>
                                    )}
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            handleRemoveFile(index);
                                        }}
                                        className="absolute top-[-3px] right-0 w-5 h-5 text-gray-500 text-base z-10"
                                    >
                                        <span className="iconfont icon-delete bg-white rounded-full"></span>
                                    </button>
                                </div>
                            </div>
                        ))}
                        {/* 添加更多文件的按钮 */}
                        {selectedFiles.length < 9 && (
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
                                                <span className="text-xs">{t('common.camera')}</span>
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
                                                <span className="text-xs">{t('common.gallery')}</span>
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
                        )}
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
                        {recordingCancelled ? t('chat.releaseToCancel') : t('chat.slideUpToCancel')}
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
                        <VoiceRecorder
                            isRecording={isRecording}
                            setIsRecording={setIsRecording}
                            onVoiceSend={handleVoiceSend}
                            isAIRunning={isAIRunning}
                            recordingCancelled={recordingCancelled}
                            setRecordingCancelled={setRecordingCancelled}
                            onToggleVoiceMode={onToggleVoiceMode}
                            selectedFiles={selectedFiles}
                            showFileOptions={showFileOptions}
                            setShowFileOptions={setShowFileOptions}
                        />
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
                                        content: t('chat.aiProcessing'),
                                        icon: 'loading',
                                        duration: 2000
                                    });
                                    return;
                                }
                                handleSendWithFiles(nextContent);
                            }}
                            placeholder={t('chat.inputPlaceholder')}
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
                                            blurInput();
                                            handleSendWithFiles(content);
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
                                                className="iconfont icon-xiangshangjiantouquan text-3xl action-icon text-gray-400 cursor-not-allowed opacity-50"
                                                onMouseDown={(e) => e.preventDefault()}
                                                onClick={() => {
                                                    blurInput();
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
                                <span className="text-xs">{t('common.camera')}</span>
                            </div>
                        </button>
                        <button
                            onClick={() => handleFileOptionClick('photo')}
                        >
                            <div className="w-22 h-22 bg-[var(--color-background-body)] rounded-xl flex flex-col items-center gap-2 justify-center">
                                <span className="iconfont icon-tupian1 text-2xl"></span>
                                <span className="text-xs">{t('common.gallery')}</span>
                            </div>
                        </button>
                        <button
                            onClick={() => handleFileOptionClick('file')}
                        >
                            <div className="w-22 h-22 bg-[var(--color-background-body)] rounded-xl flex flex-col items-center gap-2 justify-center">
                                <span className="iconfont icon-a-wenjianjiawenjian text-xl"></span>
                                <span className="text-xs">{t('common.file')}</span>
                            </div>
                        </button>
                    </div>
                </div>
            </div>

            {/* 图片查看器 */}
            <ImageViewer
                image={currentPreviewImage}
                visible={imageViewerVisible}
                onClose={() => setImageViewerVisible(false)}
            />
        </div>
    );
};
