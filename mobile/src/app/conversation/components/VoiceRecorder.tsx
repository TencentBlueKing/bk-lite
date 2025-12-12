import React, { useRef } from 'react';
import { Toast } from 'antd-mobile';
import { useTranslation } from '@/utils/i18n';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';

interface VoiceRecorderProps {
    isRecording: boolean;
    setIsRecording: (value: boolean) => void;
    onVoiceSend: (text: string) => void;
    isAIRunning: boolean;
    recordingCancelled: boolean;
    setRecordingCancelled: (value: boolean) => void;
    onToggleVoiceMode: () => void;
    selectedFiles: File[];
    onSendFiles: () => void;
    showFileOptions: boolean;
    setShowFileOptions: (value: boolean) => void;
}

export const VoiceRecorder: React.FC<VoiceRecorderProps> = ({
    isRecording,
    setIsRecording,
    onVoiceSend,
    isAIRunning,
    recordingCancelled,
    setRecordingCancelled,
    onToggleVoiceMode,
    selectedFiles,
    onSendFiles,
    showFileOptions,
    setShowFileOptions,
}) => {
    const { t } = useTranslation();
    const longPressTimerRef = useRef<NodeJS.Timeout | null>(null);
    const touchStartYRef = useRef<number>(0);
    const isLongPressRef = useRef(false);
    const isRecordingRef = useRef(false);
    const recordingStartTimeRef = useRef<number>(0);

    const {
        recognizedText,
        setRecognizedText,
        startSpeechRecognition,
        stopSpeechRecognition,
        checkMicrophonePermissionSilent,
    } = useSpeechRecognition(isLongPressRef, isRecordingRef);

    const handleVoiceTouchStart = async (e: React.TouchEvent | React.MouseEvent) => {
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

        // 先静默检查权限状态
        const hasPermission = await checkMicrophonePermissionSilent();

        // 如果权限未授予,触发权限请求但不启动 UI 和语音识别
        if (!hasPermission) {
            console.log('权限未授予,触发权限请求...');
            try {
                // 触发权限请求
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                stream.getTracks().forEach(track => track.stop());
            } catch (error) {
                console.error('权限请求失败:', error);
                Toast.show({
                    content: '无法获取麦克风权限',
                    icon: 'fail',
                    duration: 2000
                });
            }
            return; // 不继续执行后续逻辑
        }

        // 权限已授予,正常启动录音
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
                            content: t('chat.aiProcessing'),
                            icon: 'loading',
                            duration: 2000
                        });
                        setRecognizedText('');
                        return;
                    }

                    setTimeout(() => {
                        if (recognizedText && recognizedText.trim()) {
                            onVoiceSend(recognizedText.trim());
                            setRecognizedText('');
                        } else {
                            Toast.show({ content: '未识别到内容,请重试', icon: 'fail' });
                        }
                    }, 500);
                }
            }

            setRecordingCancelled(false);
        }
    };

    return (
        <>
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
                {t('chat.holdToTalk')}
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
                            onSendFiles();
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
        </>
    );
};
