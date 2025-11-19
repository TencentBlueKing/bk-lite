import { useRef, useState } from 'react';
import { Toast } from 'antd-mobile';
import { invoke } from '@tauri-apps/api/core';

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

                recognition.onstart = () => {
                    console.log('🎤 语音识别已启动');
                };

                recognition.onresult = (event: any) => {
                    let allText = '';
                    for (let i = 0; i < event.results.length; i++) {
                        allText += event.results[i][0].transcript;
                    }
                    setRecognizedText(allText);
                    console.log('📝 识别结果:', allText);
                };

                recognition.onerror = (event: any) => {
                    console.error('❌ 语音识别错误:', event.error);

                    let errorMessage = '';
                    switch (event.error) {
                        case 'not-allowed':
                            errorMessage = '请允许浏览器访问麦克风权限';
                            break;
                        case 'no-speech':
                            console.log('⏸️ 未检测到语音（静音中）');
                            return;
                        case 'audio-capture':
                            errorMessage = '未找到麦克风设备';
                            break;
                        case 'network':
                            errorMessage = '网络错误，请检查网络连接';
                            break;
                        case 'aborted':
                            console.log('🛑 语音识别已取消');
                            return;
                        default:
                            errorMessage = '语音识别失败';
                    }

                    if (errorMessage) {
                        Toast.show({ content: errorMessage, icon: 'fail', duration: 2000 });
                    }
                };

                recognition.onend = () => {
                    console.log('⏹️ 语音识别已结束');

                    if (isLongPressRef.current && isRecordingRef.current) {
                        console.log('🔄 用户仍在录音，自动重启识别...');
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

    // 检查麦克风权限 (Tauri 环境)
    const checkMicrophonePermissionTauri = async (): Promise<boolean> => {
        try {
            const result = await invoke('check_microphone_permission');
            console.log('Tauri 麦克风权限检查结果:', result);
            return true; // Tauri 环境下由原生层处理
        } catch (error) {
            console.error('Tauri 权限检查失败:', error);
            return false;
        }
    };

    // 检查麦克风权限 (Web 环境)
    const checkMicrophonePermissionWeb = async (): Promise<boolean> => {
        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                console.log('浏览器不支持 MediaDevices API');
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

    // 检查麦克风权限
    const checkMicrophonePermission = async (): Promise<boolean> => {
        // 检测是否在 Tauri 环境中
        const isTauri = '__TAURI__' in window;

        if (isTauri) {
            return await checkMicrophonePermissionTauri();
        } else {
            return await checkMicrophonePermissionWeb();
        }
    };

    // 静默检查麦克风权限状态(不会触发权限弹窗)
    const checkMicrophonePermissionSilent = async (): Promise<boolean> => {
        try {
            // 检测是否在 Tauri 环境中
            const isTauri = '__TAURI__' in window;

            if (isTauri) {
                // Tauri 环境下直接返回 true，由原生层处理
                return true;
            }

            // Web 环境：尝试多种方式检测权限

            // 方法1: 使用 Permissions API 查询权限状态(不会触发弹窗)
            if (navigator.permissions && navigator.permissions.query) {
                try {
                    const result = await navigator.permissions.query({ name: 'microphone' as PermissionName });
                    console.log('Permissions API 查询结果:', result.state);
                    if (result.state === 'granted') {
                        return true;
                    }
                    if (result.state === 'denied') {
                        return false;
                    }
                    // state === 'prompt' 时继续检测
                } catch (err) {
                    console.log(err, 'Permissions API 不支持 microphone 查询');
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
                        console.log('通过设备枚举检测到已授权');
                        return true;
                    }
                } catch (err) {
                    console.log('设备枚举失败:', err);
                }
            }

            // 如果所有检测都不确定，返回 false，让用户主动触发权限
            console.log('无法确定权限状态，需要用户主动触发');
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
                content: '语音识别需要 HTTPS 环境',
                icon: 'fail',
                duration: 2000
            });
            return;
        }

        const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (!SpeechRecognition) {
            console.log('浏览器不支持语音识别');
            Toast.show({
                content: '当前浏览器不支持语音识别',
                icon: 'fail',
                duration: 2000
            });
            return;
        }

        const hasPermission = await checkMicrophonePermission();
        console.log('麦克风权限:', hasPermission);
        if (!hasPermission) {
            Toast.show({
                content: '无法访问麦克风，请检查权限设置',
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
                    content: '语音识别启动失败',
                    icon: 'fail',
                    duration: 2000
                });
            }
        } else {
            Toast.show({
                content: '语音识别初始化失败',
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
