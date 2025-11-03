"""通用工具函数模块"""

import json
from pathlib import Path

import pandas as pd
import yaml
from loguru import logger


def flatten_json(data: dict, parent_key: str = "", sep: str = ".") -> dict:
    """将嵌套的 JSON 对象扁平化为 key path 格式

    Args:
        data: JSON 数据
        parent_key: 父级 key
        sep: 分隔符

    Returns:
        扁平化的字典，key 为 json path，value 为对应的值

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
        flat_dict: 扁平化的字典，key 为 json path
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

        # 遍历 keys，构建嵌套结构
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # 设置最后一个 key 的值
        current[keys[-1]] = value

    return result


def load_lang_packs_to_dataframe(lang_pack_path: Path) -> pd.DataFrame:
    """加载语言包目录下的所有 JSON 文件到 DataFrame

    Args:
        lang_pack_path: 语言包目录路径

    Returns:
        DataFrame，列为 key, en, zh 等
    """
    if not lang_pack_path.exists():
        logger.error(f"语言包路径不存在: {lang_pack_path}")
        return pd.DataFrame()

    # 收集所有 JSON 文件
    json_files = list(lang_pack_path.glob("*.json"))
    if not json_files:
        logger.warning(f"未找到 JSON 文件: {lang_pack_path}")
        return pd.DataFrame()

    logger.info(f"找到 {len(json_files)} 个语言包文件")

    # 存储每个语言的扁平化数据
    lang_data = {}

    for json_file in json_files:
        lang_code = json_file.stem  # 获取文件名（不含扩展名），如 'zh', 'en'
        logger.info(f"加载语言包: {lang_code}.json")

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                flattened = flatten_json(data)
                lang_data[lang_code] = flattened
        except Exception as e:
            logger.error(f"加载 {json_file} 失败: {e}")
            continue

    # 收集所有唯一的 key
    all_keys = set()
    for flattened in lang_data.values():
        all_keys.update(flattened.keys())

    all_keys = sorted(all_keys)
    logger.info(f"共有 {len(all_keys)} 个翻译 key")

    # 构建 DataFrame
    df_data = {"key": all_keys}

    for lang_code, flattened in lang_data.items():
        df_data[lang_code] = [flattened.get(key, "") for key in all_keys]

    return pd.DataFrame(df_data)


def write_lang_json_file(df: pd.DataFrame, lang_code: str, lang_pack_path: Path):
    """写入单个语言的 JSON 文件

    Args:
        df: DataFrame，包含 '名称' 列和语言列
        lang_code: 语言代码，如 'zh', 'en'
        lang_pack_path: 语言包目录路径
    """
    logger.info(f"处理语言: {lang_code}")

    # 构建扁平化字典
    flat_dict = {}
    for _, row in df.iterrows():
        key = row['名称']
        value = row[lang_code]

        # 处理空值
        if pd.isna(value) or value == '':
            value = ''
        else:
            value = str(value)

        flat_dict[key] = value

    # 还原为嵌套 JSON
    nested_json = unflatten_json(flat_dict)

    # 写入 JSON 文件
    json_file_path = lang_pack_path / f"{lang_code}.json"

    with open(json_file_path, 'w', encoding='utf-8') as f:
        json.dump(nested_json, f, ensure_ascii=False, indent=2)

    logger.success(f"已写入 {json_file_path}")


def load_yaml_packs_to_dataframe(lang_pack_path: Path) -> pd.DataFrame:
    """加载语言包目录下的所有 YAML 文件到 DataFrame

    Args:
        lang_pack_path: 语言包目录路径

    Returns:
        DataFrame，列为 key, en, zh-Hans 等
    """
    if not lang_pack_path.exists():
        logger.error(f"语言包路径不存在: {lang_pack_path}")
        return pd.DataFrame()

    # 收集所有 YAML 文件
    yaml_files = list(lang_pack_path.glob("*.yaml")) + \
        list(lang_pack_path.glob("*.yml"))
    if not yaml_files:
        logger.warning(f"未找到 YAML 文件: {lang_pack_path}")
        return pd.DataFrame()

    logger.info(f"找到 {len(yaml_files)} 个语言包文件")

    # 存储每个语言的扁平化数据
    lang_data = {}

    for yaml_file in yaml_files:
        lang_code = yaml_file.stem  # 获取文件名（不含扩展名），如 'zh-Hans', 'en'
        logger.info(f"加载语言包: {lang_code}.yaml")

        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                flattened = flatten_json(data)
                lang_data[lang_code] = flattened
        except Exception as e:
            logger.error(f"加载 {yaml_file} 失败: {e}")
            continue

    # 收集所有唯一的 key
    all_keys = set()
    for flattened in lang_data.values():
        all_keys.update(flattened.keys())

    all_keys = sorted(all_keys)
    logger.info(f"共有 {len(all_keys)} 个翻译 key")

    # 构建 DataFrame
    df_data = {"key": all_keys}

    for lang_code, flattened in lang_data.items():
        df_data[lang_code] = [flattened.get(key, "") for key in all_keys]

    return pd.DataFrame(df_data)


def write_lang_yaml_file(df: pd.DataFrame, lang_code: str, lang_pack_path: Path):
    """写入单个语言的 YAML 文件

    Args:
        df: DataFrame，包含 '名称' 列和语言列
        lang_code: 语言代码，如 'zh-Hans', 'en'
        lang_pack_path: 语言包目录路径
    """
    logger.info(f"处理语言: {lang_code}")

    # 构建扁平化字典
    flat_dict = {}
    for _, row in df.iterrows():
        key = row['名称']
        value = row[lang_code]

        # 处理空值
        if pd.isna(value) or value == '':
            value = ''
        else:
            value = str(value)

        flat_dict[key] = value

    # 还原为嵌套结构
    nested_yaml = unflatten_json(flat_dict)

    # 写入 YAML 文件
    yaml_file_path = lang_pack_path / f"{lang_code}.yaml"

    with open(yaml_file_path, 'w', encoding='utf-8') as f:
        yaml.dump(nested_yaml, f, allow_unicode=True,
                  default_flow_style=False, sort_keys=False)

    logger.success(f"已写入 {yaml_file_path}")
