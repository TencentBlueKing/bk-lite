"""内置模型语言包必须覆盖 model_config.xlsx 种子。"""

from pathlib import Path

import pandas as pd
import pytest

from apps.core.utils.loader import LanguageLoader

pytestmark = pytest.mark.unit

XLSX = Path(__file__).resolve().parents[1] / "support-files" / "model_config.xlsx"


def _xlsx_models_and_attrs():
    sheets = pd.read_excel(XLSX, sheet_name=None, header=1)
    models = {str(row.model_id): str(row.model_name) for _, row in sheets["models"].iterrows() if pd.notna(row.model_id)}
    attrs = {}
    for model_id in models:
        mapping = {}
        for _, row in sheets[f"attr-{model_id}"].iterrows():
            if pd.isna(row.get("attr_id")):
                continue
            mapping[str(row.attr_id)] = None if pd.isna(row.get("attr_name")) else str(row.attr_name)
        attrs[model_id] = mapping
    classifications = {
        str(row.classification_id): str(row.classification_name) for _, row in sheets["classifications"].iterrows() if pd.notna(row.classification_id)
    }
    return models, classifications, attrs


def test_language_pack_covers_xlsx_models():
    models, classifications, attrs = _xlsx_models_and_attrs()
    en = LanguageLoader("cmdb", "en").translations
    zh = LanguageLoader("cmdb", "zh-Hans").translations

    missing_model_en = sorted(mid for mid in models if mid not in (en.get("MODEL") or {}))
    missing_model_zh = sorted(mid for mid in models if mid not in (zh.get("MODEL") or {}))
    missing_cls_en = sorted(cid for cid in classifications if cid not in (en.get("CLASSIFICATION") or {}))
    missing_attr = []
    for model_id, mapping in attrs.items():
        en_map = (en.get("ATTR") or {}).get(model_id) or {}
        zh_map = (zh.get("ATTR") or {}).get(model_id) or {}
        for attr_id in mapping:
            if attr_id not in en_map or attr_id not in zh_map:
                missing_attr.append(f"{model_id}.{attr_id}")

    assert missing_model_en == []
    assert missing_model_zh == []
    assert missing_cls_en == []
    assert missing_attr == []
    assert en["MODEL"]["kingbase"] == "KingbaseES"
    assert zh["MODEL"]["kingbase"] == "人大金仓KingbaseES"
