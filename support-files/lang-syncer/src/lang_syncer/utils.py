"""通用工具函数模块"""

import json
from pathlib import Path

import pandas as pd
import yaml
from loguru import logger

from lang_syncer.exceptions import FileOperationError


def flatten_json(data: dict, parent_key: str = "", sep: str = ".") -> dict:
    """将嵌套的 JSON 对象扁平化为 key path 格式

    Args:
        data: JSON 数据
        parent_key: 父级 key
        sep: 分隔符

    Returns:
        扁平化的字典

    Example:
        {"common": {"actions": "操作"}} -> {"common.actions": "操作"}
    """
    items = []
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_json(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def unflatten_json(flat_dict: dict, sep: str = ".") -> dict:
    """将扁平化的 key path 格式还原为嵌套的 JSON 对象

    Args:
        flat_dict: 扁平化的字典
        sep: 分隔符

    Returns:
        嵌套的 JSON 对象

    Example:
        {"common.actions": "操作"} -> {"common": {"actions": "操作"}}
    """
    result = {}

    for flat_key, value in flat_dict.items():
        keys = flat_key.split(sep)
        current = result

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    return result


def _load_files_to_dataframe(lang_pack_path: Path, file_pattern: str, loader_func) -> pd.DataFrame:
    """通用的文件加载函数

    Args:
        lang_pack_path: 语言包目录路径
        file_pattern: 文件匹配模式（如 "*.json", "*.yaml"）
        loader_func: 文件加载函数

    Returns:
        DataFrame，列为 key 和各语言代码

    Raises:
        FileOperationError: 文件操作失败
    """
    if not lang_pack_path.exists():
        raise FileOperationError(f"语言包路径不存在: {lang_pack_path}")

    # 收集文件
    files = list(lang_pack_path.glob(file_pattern))
    if not files:
        logger.warning(f"未找到匹配的文件: {lang_pack_path}/{file_pattern}")
        return pd.DataFrame()

    logger.info(f"找到 {len(files)} 个语言包文件")

    # 加载每个语言的数据
    lang_data = {}
    for file in files:
        lang_code = file.stem
        logger.info(f"加载语言包: {file.name}")

        try:
            with open(file, "r", encoding="utf-8") as f:
                data = loader_func(f)
                if data:
                    lang_data[lang_code] = flatten_json(data)
        except Exception as e:
            logger.error(f"加载 {file} 失败: {e}")
            continue

    if not lang_data:
        return pd.DataFrame()

    # 构建 DataFrame
    all_keys = sorted(set().union(*[d.keys() for d in lang_data.values()]))
    logger.info(f"共有 {len(all_keys)} 个翻译 key")

    df_data = {"key": all_keys}
    for lang_code, flattened in lang_data.items():
        df_data[lang_code] = [flattened.get(key, "") for key in all_keys]

    return pd.DataFrame(df_data)


def load_lang_packs_to_dataframe(lang_pack_path: Path) -> pd.DataFrame:
    """加载 JSON 格式语言包到 DataFrame

    Args:
        lang_pack_path: 语言包目录路径

    Returns:
        DataFrame，列为 key 和各语言代码
    """
    return _load_files_to_dataframe(lang_pack_path, "*.json", json.load)


def load_yaml_packs_to_dataframe(lang_pack_path: Path) -> pd.DataFrame:
    """加载 YAML 格式语言包到 DataFrame

    Args:
        lang_pack_path: 语言包目录路径

    Returns:
        DataFrame，列为 key 和各语言代码
    """
    return _load_files_to_dataframe(lang_pack_path, "*.yaml", yaml.safe_load)


def _write_lang_file(df: pd.DataFrame, lang_code: str, lang_pack_path: Path, file_ext: str, dumper_func):
    """通用的语言文件写入函数

    Args:
        df: DataFrame，包含 '名称' 列和语言列
        lang_code: 语言代码
        lang_pack_path: 语言包目录路径
        file_ext: 文件扩展名（如 "json", "yaml"）
        dumper_func: 数据写入函数

    Raises:
        FileOperationError: 文件操作失败
    """
    logger.info(f"处理语言: {lang_code}")

    # 构建扁平化字典
    flat_dict = {}
    for _, row in df.iterrows():
        key = row["名称"]
        value = row[lang_code]

        # 处理空值
        if pd.isna(value) or value == "":
            value = ""
        else:
            value = str(value)

        flat_dict[key] = value

    # 还原为嵌套结构
    nested_data = unflatten_json(flat_dict)

    # 写入文件
    file_path = lang_pack_path / f"{lang_code}.{file_ext}"

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            dumper_func(nested_data, f)
        logger.success(f"已写入 {file_path}")
    except Exception as e:
        raise FileOperationError(f"写入文件失败 {file_path}: {e}")


def write_lang_json_file(df: pd.DataFrame, lang_code: str, lang_pack_path: Path):
    """写入 JSON 格式语言文件

    Args:
        df: DataFrame，包含 '名称' 列和语言列
        lang_code: 语言代码
        lang_pack_path: 语言包目录路径
    """

    def json_dumper(data, f):
        json.dump(data, f, ensure_ascii=False, indent=2)

    _write_lang_file(df, lang_code, lang_pack_path, "json", json_dumper)


def write_lang_yaml_file(df: pd.DataFrame, lang_code: str, lang_pack_path: Path):
    """写入 YAML 格式语言文件

    Args:
        df: DataFrame，包含 '名称' 列和语言列
        lang_code: 语言代码
        lang_pack_path: 语言包目录路径
    """

    def yaml_dumper(data, f):
        yaml.dump(data, f, allow_unicode=True,
                  default_flow_style=False, sort_keys=False)

    _write_lang_file(df, lang_code, lang_pack_path, "yaml", yaml_dumper)
