"""Server 后端语言包同步模块"""

from pathlib import Path

import pandas as pd
from tqdm import tqdm

from lang_syncer.base_syncer import BaseLangSyncer
from lang_syncer.config import AppConfig, Config
from lang_syncer.utils import load_yaml_packs_to_dataframe, write_lang_yaml_file


class ServerLangSyncer(BaseLangSyncer):
    """Server 后端语言包同步器"""

    def _get_lang_pack_path(self, app_name: str) -> Path:
        """获取语言包路径"""
        return Config.SERVER_ROOT / app_name / "language"

    def _load_lang_packs(self, lang_pack_path: Path) -> pd.DataFrame:
        """加载 YAML 格式语言包"""
        return load_yaml_packs_to_dataframe(lang_pack_path)

    def _write_lang_file(self, df: pd.DataFrame, lang_code: str, lang_pack_path: Path):
        """写入 YAML 格式语言文件"""
        write_lang_yaml_file(df, lang_code, lang_pack_path)

    def _build_properties_list(self, df: pd.DataFrame) -> list[dict]:
        """构建 Notion properties 列表（Server 格式）"""
        properties_list = []
        for _, row in tqdm(df.iterrows(), total=len(df), desc="构建数据"):
            properties = {
                "名称": {"title": [{"text": {"content": row["key"]}}]},
                "zh-Hans": {"rich_text": [{"text": {"content": str(row.get("zh-Hans", ""))}}]},
                "en": {"rich_text": [{"text": {"content": str(row.get("en", ""))}}]},
            }
            properties_list.append(properties)
        return properties_list
