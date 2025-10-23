"""
分析已安装 Python 包的磁盘占用情况
Usage: python who_is_big.py [TOP_N]
"""
from importlib import metadata as md
from pathlib import Path
from typing import List, Tuple, Optional
import sys
from tqdm import tqdm


def format_size(size_bytes: int) -> str:
    """格式化字节数为人类可读的大小表示"""
    if size_bytes == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    
    for unit in units:
        if size < 1024.0 or unit == "TB":
            return f"{size:6.1f} {unit}"
        size /= 1024.0
    
    return f"{size:6.1f} TB"


def calculate_path_size(path: Path) -> int:
    """安全地计算路径（文件或目录）的总大小"""
    total_size = 0
    
    try:
        if path.is_file():
            total_size = path.stat().st_size
        elif path.is_dir():
            for file_path in path.rglob("*"):
                if file_path.is_file():
                    try:
                        total_size += file_path.stat().st_size
                    except (OSError, PermissionError):
                        # 跳过无法访问的文件
                        continue
    except (OSError, PermissionError):
        # 路径不存在或无权限访问
        pass
    
    return total_size


def get_distribution_size(dist) -> Tuple[int, str]:
    """获取单个发行版的大小和名称"""
    try:
        files = dist.files or []
    except Exception:
        files = []
    
    total_size = 0
    for file_info in files:
        try:
            file_path = dist.locate_file(file_info)
            total_size += calculate_path_size(file_path)
        except Exception:
            # 跳过无法定位的文件
            continue
    
    package_name = dist.metadata.get("Name", "Unknown")
    return total_size, package_name


def analyze_packages(top_n: int) -> List[Tuple[int, str]]:
    """分析所有已安装包的大小"""
    distributions = list(md.distributions())
    results = []
    
    for dist in tqdm(distributions, desc="Analyzing packages", unit="pkg"):
        size, name = get_distribution_size(dist)
        results.append((size, name))
    
    # 按大小降序排序
    results.sort(reverse=True, key=lambda x: x[0])
    return results[:top_n]


def main() -> None:
    """主函数"""
    # 解析命令行参数
    try:
        top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
        if top_n <= 0:
            raise ValueError("TOP_N must be positive")
    except ValueError as e:
        print(f"Error: Invalid TOP_N argument. {e}")
        print("Usage: python who_is_big.py [TOP_N]")
        sys.exit(1)
    
    # 分析包大小
    try:
        package_sizes = analyze_packages(top_n)
    except KeyboardInterrupt:
        print("\nAnalysis interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error during analysis: {e}")
        sys.exit(1)
    
    # 输出结果
    print(f"\nInstalled distributions by size (Top {top_n}):")
    print("-" * 50)
    
    total_analyzed_size = 0
    for size, name in package_sizes:
        print(f"{format_size(size)}  {name}")
        total_analyzed_size += size
    
    if package_sizes:
        print("-" * 50)
        print(f"{'Total:':<12} {format_size(total_analyzed_size)}")


if __name__ == "__main__":
    main()