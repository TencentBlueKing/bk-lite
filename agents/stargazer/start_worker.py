#!/usr/bin/env python
# -- coding: utf-8 --
# @File: start_worker.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
启动 ARQ Worker 的脚本
用于处理异步采集任务

生产环境增强：
- 优雅停机（SIGTERM/SIGINT 信号处理）
- 进程守护支持
"""
import sys
import os
import signal

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arq import run_worker
from core.worker import WorkerSettings

# 全局标志，用于优雅停机
shutdown_flag = False


def signal_handler(signum, frame):
    """
    信号处理器 - 优雅停机

    当收到 SIGTERM 或 SIGINT 信号时，标记停机标志
    Worker 会等待当前任务执行完毕后再退出
    """
    global shutdown_flag
    signal_name = signal.Signals(signum).name
    print(f"\n[Worker] Received {signal_name} signal, shutting down gracefully...")
    print("[Worker] Waiting for current tasks to complete...")
    shutdown_flag = True


if __name__ == '__main__':
    """
    运行 ARQ Worker
    
    使用方法：
        python start_worker.py
    
    优雅停机：
        kill -TERM <pid>  # 发送 SIGTERM 信号
        Ctrl+C            # 发送 SIGINT 信号
    """
    # 注册信号处理器
    signal.signal(signal.SIGTERM, signal_handler)  # systemd/supervisor 停止信号
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C

    print("=" * 60)
    print("Starting ARQ Worker with graceful shutdown support")
    print("Press Ctrl+C or send SIGTERM to stop gracefully")
    print("=" * 60)

    try:
        # 运行 Worker
        run_worker(WorkerSettings)
    except KeyboardInterrupt:
        print("\n[Worker] Keyboard interrupt received")
    except Exception as e:
        print(f"[Worker] Fatal error: {e}")
        sys.exit(1)
    finally:
        print("[Worker] Shutdown complete")
