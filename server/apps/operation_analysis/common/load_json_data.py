# -- coding: utf-8 --
# @File: load_json_data.py
# @Time: 2025/11/6 
# @Author: windyzhao

import json
from pathlib import Path
from typing import Union, List, Dict


def load_support_json(filename: str) -> Union[List[Dict], Dict]:
    """
    从support-files目录加载JSON数据文件
    
    :param filename: JSON文件名(如 'namespace.json', 'tags.json', 'source_api.json' 等)
    :return: 解析后的JSON数据(列表或字典)
    :raises FileNotFoundError: 文件不存在时抛出
    :raises json.JSONDecodeError: JSON格式错误时抛出
    """
    # 获取support-files目录的路径
    support_files_dir = Path(__file__).parent.parent / "support-files"
    json_file = support_files_dir / filename
    
    if not json_file.exists():
        raise FileNotFoundError(f"数据文件不存在: {json_file}")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.load(f)
