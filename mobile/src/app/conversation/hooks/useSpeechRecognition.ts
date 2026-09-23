import { useRef, useState } from 'react';
import { Toast } from 'antd-mobile';
import { useTranslation } from '@/utils/i18n';

interface UseSpeechRecognitionReturn {
    recognizedText: string;
    setRecognizedText: (text: string) => void;
    initSpeechRecognition: () => void;
    startSpeechRecognition: () => Promise<void>;
    stopSpeechRecognition: () => void;
    checkMicrophonePermissionSilent: () => Promise<boolean>;
}

export const useSpeechRecognition = (
    isLongPressRef: React.MutableRefObject<boolean>,
    isRecordingRef: React.MutableRefObject<boolean>
): UseSpeechRecognitionReturn => {
    const { t } = useTranslation();
    const recognitionRef = useRef<any>(null);
    const [recognizedText, setRecognizedText] = useState('');

    // 初始化语音识别
    const initSpeechRecognition = () => {
        if (!recognitionRef.current) {
            const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

            if (SpeechRecognition) {
                const recognition = new SpeechRecognition();
                recognition.lang = 'zh-CN';
                recognition.continuous = true;
                recognition.interimResults = true;
                recognition.maxAlternatives = 1;

                recognition.onresult = (event: any) => {
                    let allText = '';
                    for (let i = 0; i < event.results.length; i++) {
                        allText += event.results[i][0].transcript;
                    }
                    setRecognizedText(allText);
                };

                recognition.onerror = (event: any) => {
                    console.error('❌ 语音识别错误:', event.error);

                    let errorMessage = '';
                    switch (event.error) {
                        case 'not-allowed':
                            errorMessage = t('chat.microphonePermissionRequired');
                            break;
                        case 'no-speech':
                            return;
                        case 'audio-capture':
                            errorMessage = t('chat.microphoneNotFound');
                            break;
                        case 'network':
                            errorMessage = t('chat.speechNetworkError');
                            break;
                        case 'aborted':
                            return;
                        default:
                            errorMessage = t('chat.speechRecognitionFailed');
                    }

                    if (errorMessage) {
                        Toast.show({ content: errorMessage, icon: 'fail', duration: 2000 });
                    }
                };

                recognition.onend = () => {
                    if (isLongPressRef.current && isRecordingRef.current) {
                        try {
                            recognition.start();
                        } catch (error) {
                            console.error('重启识别失败:', error);
                        }
                    }
                };

                recognitionRef.current = recognition;
            }
        }
    };

    // 检查麦克风权限（通过 getUserMedia，同时适用于 Web 和 Tauri/Android 环境）
    // 在 Android Tauri 中，getUserMedia 会经由 WebChromeClient.onPermissionRequest
    // 触发系统标准权限弹窗，无需额外的 IPC 命令。
    const checkMicrophonePermission = async (): Promise<boolean> => {
        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                return false;
            }

            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            stream.getTracks().forEach(track => track.stop());
            return true;
        } catch (error) {
            console.error('麦克风权限检查失败:', error);
            return false;
        }
    };

    // 静默检查麦克风权限状态（不会触发权限弹窗）
    const checkMicrophonePermissionSilent = async (): Promise<boolean> => {
        try {
            // 方法1: 使用 Permissions API 查询权限状态（不会触发弹窗）
            if (navigator.permissions && navigator.permissions.query) {
                try {
                    const result = await navigator.permissions.query({ name: 'microphone' as PermissionName });
                    if (result.state === 'granted') {
                        return true;
                    }
                    if (result.state === 'denied') {
                        return false;
                    }
                    // state === 'prompt' 时继续检测
                } catch {
                }
            }

            // 方法2: 尝试枚举设备（已授权时不会触发弹窗）
            if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
                try {
                    const devices = await navigator.mediaDevices.enumerateDevices();
                    const audioInputs = devices.filter(device => device.kind === 'audioinput');
                    // 如果能获取到设备标签，说明已有权限
                    const hasLabels = audioInputs.some(device => device.label !== '');
                    if (hasLabels) {
                        return true;
                    }
                } catch {
                }
            }

            // 如果所有检测都不确定，返回 false，让用户主动触发权限
            return false;
        } catch (error) {
            console.error('静默权限检查失败:', error);
            return false;
        }
    };

    // 开始语音识别
    const startSpeechRecognition = async () => {
        const isSecureContext = window.isSecureContext;
        if (!isSecureContext) {
            Toast.show({
                content: t('chat.speechRecognitionRequiresHttps'),
                icon: 'fail',
                duration: 2000
            });
            return;
        }

        const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (!SpeechRecognition) {
            Toast.show({
                content: t('chat.speechRecognitionUnsupported'),
                icon: 'fail',
                duration: 2000
            });
            return;
        }

        const hasPermission = await checkMicrophonePermission();
        if (!hasPermission) {
            Toast.show({
                content: t('chat.microphoneAccessDenied'),
                icon: 'fail',
                duration: 2000
            });
            return;
        }

        initSpeechRecognition();

        if (recognitionRef.current) {
            try {
                recognitionRef.current.start();
            } catch (error) {
                console.error('启动语音识别失败:', error);
                Toast.show({
                    content: t('chat.speechRecognitionStartFailed'),
                    icon: 'fail',
                    duration: 2000
                });
            }
        } else {
            Toast.show({
                content: t('chat.speechRecognitionInitFailed'),
                icon: 'fail',
                duration: 2000
            });
        }
    };

    // 停止语音识别
    const stopSpeechRecognition = () => {
        if (recognitionRef.current) {
            try {
                recognitionRef.current.stop();
            } catch (error) {
                console.error('停止语音识别失败:', error);
            }
        }
    };

    return {
        recognizedText,
        setRecognizedText,
        initSpeechRecognition,
        startSpeechRecognition,
        stopSpeechRecognition,
        checkMicrophonePermissionSilent,
    };
};
