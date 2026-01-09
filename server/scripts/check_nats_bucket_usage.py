#!/usr/bin/env python3
"""
查询 NATS JetStream Object Store (桶) 的容量配置和使用情况
"""
import asyncio
import os
import sys
from pathlib import Path

# 获取项目根目录（scripts 的父目录）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 切换到项目根目录（Django 需要）
os.chdir(project_root)

# 设置 Django settings 模块
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

import django
django.setup()

from nats_client.clients import get_nc_client
from config.components.nats import NATS_NAMESPACE


def format_bytes(bytes_size):
    """格式化字节大小为易读格式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


async def check_bucket_usage(bucket_name=NATS_NAMESPACE):
    """查询桶的容量配置和使用情况"""
    nc = None
    try:
        # 连接到 NATS
        nc = await get_nc_client()
        js = nc.jetstream()
        
        print("=" * 70)
        print(f"NATS JetStream Object Store 容量查询")
        print("=" * 70)
        print(f"桶名称: {bucket_name}")
        print("-" * 70)
        
        try:
            # 获取 Object Store
            object_store = await js.object_store(bucket_name)
            
            # 获取底层 Stream 信息（Object Store 底层是 Stream）
            # Object Store 的 Stream 名称格式: OBJ_<bucket_name>
            stream_name = f"OBJ_{bucket_name}"
            stream_info = await js.stream_info(stream_name)
            
            # 提取配置信息
            config = stream_info.config
            state = stream_info.state
            
            # 容量配置
            max_bytes = config.max_bytes
            max_bytes_str = "无限制" if max_bytes == -1 else format_bytes(max_bytes)
            
            # 使用情况
            used_bytes = state.bytes
            used_bytes_str = format_bytes(used_bytes)
            
            # 计算使用率
            if max_bytes > 0:
                usage_percent = (used_bytes / max_bytes) * 100
                usage_bar_length = 50
                filled_length = int(usage_bar_length * used_bytes // max_bytes)
                bar = '█' * filled_length + '░' * (usage_bar_length - filled_length)
            else:
                usage_percent = 0
                bar = '░' * 50
            
            # 显示结果
            print(f"\n📦 容量配置:")
            print(f"   最大容量 (max_bytes): {max_bytes_str}")
            if max_bytes > 0:
                print(f"   原始值: {max_bytes:,} 字节")
            
            print(f"\n💾 使用情况:")
            print(f"   已使用容量: {used_bytes_str}")
            print(f"   原始值: {used_bytes:,} 字节")
            print(f"   文件数量: {state.messages}")
            
            if max_bytes > 0:
                print(f"\n📊 使用率:")
                print(f"   [{bar}] {usage_percent:.2f}%")
                print(f"   剩余容量: {format_bytes(max_bytes - used_bytes)}")
                
                # 告警提示
                if usage_percent >= 95:
                    print(f"\n⚠️  警告: 容量使用率超过 95%，建议立即清理或扩容！")
                elif usage_percent >= 85:
                    print(f"\n⚠️  警告: 容量使用率超过 85%，请关注容量使用情况")
                elif usage_percent >= 70:
                    print(f"\n💡 提示: 容量使用率超过 70%，可以开始规划清理策略")
            
            # 列出所有对象
            print(f"\n📋 存储对象列表:")
            entries = await object_store.list()
            if entries:
                print(f"   总共 {len(entries)} 个对象:")
                print(f"\n   {'对象名称':<40} {'大小':<15} {'修改时间'}")
                print(f"   {'-' * 40} {'-' * 15} {'-' * 25}")
                for entry in entries:
                    size_str = format_bytes(entry.size)
                    # 处理 mtime 可能为字符串或 datetime 对象的情况
                    if entry.mtime:
                        if isinstance(entry.mtime, str):
                            modified = entry.mtime
                        else:
                            modified = entry.mtime.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        modified = 'N/A'
                    print(f"   {entry.name:<40} {size_str:<15} {modified}")
            else:
                print(f"   (空桶)")
            
            print("\n" + "=" * 70)
            
        except Exception as e:
            if "not found" in str(e).lower():
                print(f"\n❌ 错误: 桶 '{bucket_name}' 不存在")
                print(f"提示: 请先运行应用创建桶，或检查桶名称是否正确")
            else:
                print(f"\n❌ 错误: {e}")
                raise
            
    except Exception as e:
        print(f"\n❌ 连接 NATS 失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if nc:
            await nc.close()


if __name__ == "__main__":
    # 支持命令行参数指定桶名称
    bucket_name = sys.argv[1] if len(sys.argv) > 1 else NATS_NAMESPACE
    asyncio.run(check_bucket_usage(bucket_name))
