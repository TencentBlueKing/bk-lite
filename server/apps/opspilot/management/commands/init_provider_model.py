import json

from django.core.management import BaseCommand

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import EmbedProvider, LLMModel, ModelType, OCRProvider, RerankProvider
from apps.system_mgmt.models import Group


class Command(BaseCommand):
    help = "初始化模型数据"

    def handle(self, *args, **options):
        group_id = Group.objects.get_or_create(name="Default", parent_id=0)[0].id
        try:
            self.create_or_update_model_type()
            model_type_map = dict(ModelType.objects.all().values_list("name", "id"))
            self.create_or_update_llm_model(group_id, model_type_map)
            self.create_or_update_embed_model(group_id, model_type_map)
            self.create_or_update_rerank_model(group_id, model_type_map)
            self.create_or_update_ocr_model(group_id, model_type_map)
        except Exception as e:
            logger.exception(e)

    @staticmethod
    def create_or_update_llm_model(group_id, model_type_map):
        llm_model_file = "apps/opspilot/management/json_file/llm_model.json"
        with open(llm_model_file, "r", encoding="utf-8") as f:
            llm_model_list = json.load(f)
        exist_llm = {i.name: i for i in LLMModel.objects.filter(is_build_in=True)}
        create_llm_model = []
        update_llm_model = []
        for i in llm_model_list:
            if i["name"] not in exist_llm:
                create_llm_model.append(
                    LLMModel(
                        name=i["name"],
                        model_type_id=model_type_map.get(i["model_type"], None),
                        is_build_in=True,
                        enabled=False,
                        team=[group_id],
                        label=i.get("label", ""),
                        llm_config={
                            "openai_api_key": "your_openai_api_key",
                            "openai_base_url": i["openai_base_url"],
                            "temperature": 0.7,
                            "model": i["model"],
                            "is_demo": True,
                        },
                    )
                )
            else:
                llm_model = exist_llm[i["name"]]
                llm_model.label = i.get("label", "")
                update_llm_model.append(llm_model)
        if create_llm_model:
            LLMModel.objects.bulk_create(create_llm_model)
            print(f"Created {len(create_llm_model)} llm models")
        if update_llm_model:
            LLMModel.objects.bulk_update(update_llm_model, ["label"])
            print(f"Updated {len(update_llm_model)} llm models")

    @staticmethod
    def create_or_update_embed_model(group_id, model_type_map):
        embed_model_file = "apps/opspilot/management/json_file/embed_model.json"
        with open(embed_model_file, "r", encoding="utf-8") as f:
            embed_model_list = json.load(f)
        exist_embed = {i.name: i for i in EmbedProvider.objects.filter(is_build_in=True)}
        create_embed_model = []
        for i in embed_model_list:
            if i["name"] not in exist_embed:
                create_embed_model.append(
                    EmbedProvider(
                        name=i["name"],
                        model_type_id=model_type_map.get(i["model_type"], None),
                        is_build_in=True,
                        enabled=False,
                        team=[group_id],
                        embed_config={
                            "base_url": i["base_url"],
                            "api_key": "your_openai_api_key",
                            "model": i["model"],
                        },
                    )
                )
        if create_embed_model:
            EmbedProvider.objects.bulk_create(create_embed_model)
            print(f"Created {len(create_embed_model)} embed models")

    @staticmethod
    def create_or_update_rerank_model(group_id, model_type_map):
        rerank_model_file = "apps/opspilot/management/json_file/rerank_model.json"
        with open(rerank_model_file, "r", encoding="utf-8") as f:
            rerank_model_list = json.load(f)
        exist_rerank = {i.name: i for i in RerankProvider.objects.filter(is_build_in=True)}
        create_rerank_model = []
        for i in rerank_model_list:
            if i["name"] not in exist_rerank:
                create_rerank_model.append(
                    RerankProvider(
                        name=i["name"],
                        model_type_id=model_type_map.get(i["model_type"], None),
                        enabled=False,
                        is_build_in=True,
                        team=[group_id],
                        rerank_config={
                            "base_url": i["base_url"],
                            "api_key": "your_openai_api_key",
                            "model": i["model"],
                        },
                    )
                )
        if create_rerank_model:
            RerankProvider.objects.bulk_create(create_rerank_model)
            print(f"Created {len(create_rerank_model)} rerank models")

    @staticmethod
    def create_or_update_model_type():
        mode_type_file = "apps/opspilot/management/json_file/mode_type.json"
        with open(mode_type_file, "r", encoding="utf-8") as f:
            model_type_data = json.load(f)
        exist_model_type = {i.name: i for i in ModelType.objects.all()}
        create_model_type = []
        update_model_type = []
        model_type = ModelType.objects.last()
        if model_type:
            index = model_type.index + 1
        else:
            index = 0
        for i in model_type_data:
            if i["name"] not in exist_model_type:
                i["is_build_in"] = True
                i["index"] = index
                create_model_type.append(ModelType(**i))
                index += 1
            else:
                update_model = exist_model_type[i["name"]]
                update_model.tags = i.get("tags", [])
                update_model_type.append(update_model)
        if create_model_type:
            ModelType.objects.bulk_create(create_model_type)
            print(f"Created {len(create_model_type)} model types")
        if update_model_type:
            ModelType.objects.bulk_update(update_model_type, ["tags"])
            print(f"Updated {len(update_model_type)} model types")

    @staticmethod
    def create_or_update_ocr_model(group_id, model_type_map):
        ocr_model_file = "apps/opspilot/management/json_file/ocr_model.json"
        with open(ocr_model_file, "r", encoding="utf-8") as f:
            ocr_model_list = json.load(f)
        exist_ocr = {i.name: i for i in OCRProvider.objects.filter(is_build_in=True)}
        create_ocr_model = []
        for i in ocr_model_list:
            if i["name"] not in exist_ocr:
                ocr_config = {
                    "base_url": i["base_url"],
                    "api_key": "your_openai_api_key",
                }
                if i["name"] == "AzureOCR":
                    ocr_config["endpoint"] = ""
                create_ocr_model.append(
                    OCRProvider(
                        name=i["name"],
                        model_type_id=model_type_map.get(i["model_type"], None),
                        enabled=False,
                        is_build_in=True,
                        team=[group_id],
                        ocr_config=ocr_config,
                    )
                )

        if create_ocr_model:
            OCRProvider.objects.bulk_create(create_ocr_model)
            print(f"Created {len(create_ocr_model)} ocr models")
