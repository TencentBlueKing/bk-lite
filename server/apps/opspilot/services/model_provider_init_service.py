from apps.opspilot.models import EmbedProvider, LLMModel, LLMSkill, OCRProvider, RerankProvider, SkillTools
from apps.opspilot.services.skill_init_json import SKILL_LIST


class ModelProviderInitService:
    def __init__(self, owner):
        self.owner = owner
        self.group_id = self.get_group_id()

    @staticmethod
    def get_group_id():
        try:
            from apps.system_mgmt.models import Group

            group, _ = Group.objects.get_or_create(name="Default", parent_id=0)
            return group.id
        except Exception:
            from apps.rpc.system_mgmt import SystemMgmt

            client = SystemMgmt()
            res = client.get_group_id("Default")
            if not res["result"]:
                return 0
            return res["data"]

    def init(self):
        if self.owner == "admin":
            RerankProvider.objects.get_or_create(
                name="bce-reranker-base_v1",
                is_build_in=True,
                defaults={
                    "rerank_config": {
                        "base_url": "local:bce:maidalun1020/bce-reranker-base_v1",
                        "api_key": "bklite",
                        "model": "bce-reranker-base_v1",
                    },
                    "team": [self.group_id],
                },
            )

            EmbedProvider.objects.get_or_create(
                name="bce-embedding-base_v1",
                is_build_in=True,
                defaults={
                    "embed_config": {
                        "base_url": "local:huggingface_embedding:maidalun1020/bce-embedding-base_v1",
                        "api_key": "bklite",
                        "model": "bce-embedding-base_v1",
                    },
                    "team": [self.group_id],
                },
            )

            EmbedProvider.objects.get_or_create(
                name="FastEmbed(BAAI/bge-small-zh-v1.5)",
                is_build_in=True,
                defaults={
                    "embed_config": {
                        "base_url": "local:huggingface_embedding:BAAI/bge-small-zh-v1.5",
                        "api_key": "bklite",
                        "model": "FastEmbed(BAAI/bge-small-zh-v1.5)",
                    },
                    "team": [self.group_id],
                },
            )

            LLMModel.objects.get_or_create(
                name="GPT-4o",
                is_build_in=True,
                defaults={
                    "team": [self.group_id],
                    "llm_config": {
                        "openai_api_key": "your_openai_api_key",
                        "openai_base_url": "https://api.openai.com",
                        "temperature": 0.7,
                        "model": "gpt-4o",
                        "is_demo": True,
                    },
                },
            )

        OCRProvider.objects.get_or_create(
            name="PaddleOCR",
            is_build_in=True,
            defaults={
                "team": [self.group_id],
                "enabled": True,
                "ocr_config": {
                    "base_url": "local:ocr:paddleocr",
                    "api_key": "bklite",
                },
            },
        )

        OCRProvider.objects.get_or_create(
            name="AzureOCR",
            is_build_in=True,
            defaults={
                "team": [self.group_id],
                "enabled": True,
                "ocr_config": {
                    "base_url": "http://ocr-server/azure_ocr",
                    "api_key": "",
                    "endpoint": "",
                },
            },
        )
        OCRProvider.objects.get_or_create(
            name="OlmOCR",
            is_build_in=True,
            defaults={
                "team": [self.group_id],
                "enabled": True,
                "ocr_config": {"base_url": "http://ocr-server/olm_ocr", "api_key": ""},
            },
        )
        tools = [
            SkillTools.objects.update_or_create(
                name="DuckDuckGo Search",
                defaults={
                    "params": {
                        "url": "langchain:duckduckgo",
                        "name": "DuckDuckGo Search",
                    },
                    "description": """Perform fast web searches using DuckDuckGo.

This tool allows you to search the internet and retrieve relevant results in real time.
You can specify the search query and control the number of results returned.
Ideal for getting up-to-date information without tracking or ads.
""",
                    "tags": ["search"],
                    "icon": "",
                    "is_build_in": True,
                },
            )[0],
            SkillTools.objects.update_or_create(
                name="Current Time Tool",
                defaults={
                    "params": {
                        "url": "langchain:current_time",
                        "name": "Current Time Tool",
                    },
                    "description": """Provides the current date and time.

Use this tool to get the exact current timestamp in `YYYY-MM-DD HH:MM:SS` format.
Useful for logging, scheduling, or any functionality that requires up-to-date time information.
""",
                    "tags": ["general"],
                    "icon": "",
                    "is_build_in": True,
                },
            )[0],
            SkillTools.objects.update_or_create(
                name="Kubernetes Insight Tools",
                defaults={
                    "params": {
                        "url": "langchain:kubernetes",
                        "name": "Kubernetes Insight Tools",
                        "kwargs": [
                            {
                                "key": "kubeconfig_path",
                                "value": "",
                                "type": "text",
                                "isRequired": True,
                            }
                        ],
                    },
                    "description": (
                        "A collection of user-friendly tools for exploring and monitoring your Kubernetes cluster.\n\n"
                        "These tools allow you to:\n\n"
                        "- 🔍 List **namespaces**, **pods**, **deployments**, **services**, and **nodes**\n"
                        "- 🚨 View recent **events** across the cluster\n"
                        "- ⚠️ Troubleshoot **failed** or **pending** pods\n\n"
                        "Each tool provides clean JSON output, making it easy to plug into chains or agents.\n\n"
                        "**Configure once** with your kubeconfig path and use anywhere."
                    ),
                    "tags": ["maintenance"],
                    "icon": "",
                    "is_build_in": True,
                },
            )[0],
            SkillTools.objects.update_or_create(
                name="Jenkins",
                defaults={
                    "params": {
                        "url": "langchain:jenkins",
                        "name": "Jenkins",
                        "kwargs": [
                            {
                                "key": "jenkins_url",
                                "value": "",
                                "type": "text",
                                "isRequired": True,
                            },
                            {
                                "key": "jenkins_username",
                                "value": "",
                                "type": "text",
                                "isRequired": True,
                            },
                            {
                                "key": "jenkins_password",
                                "value": "",
                                "type": "password",
                                "isRequired": True,
                            },
                        ],
                    },
                    "description": """### Jenkins Tools

This toolset allows you to interact with Jenkins servers for CI/CD automation.
It includes tools to:

- 🔍 **List available Jenkins jobs** — useful when you're unsure what to build.
- 🚀 **Trigger a Jenkins job build** — safely initiate a build, with validation to avoid disabled or unknown jobs.

**Use cases**:
- Discover available jobs before execution.
- Trigger builds programmatically with parameters.
- Integrate Jenkins pipelines into your LangChain workflow.

Make sure to provide valid credentials and Jenkins server URL before using.
""",
                    "tags": [
                        "maintenance",
                    ],
                    "icon": "",
                    "is_build_in": True,
                },
            )[0],
        ]
        for i in tools:
            if self.group_id not in i.team:
                i.team.append(self.group_id)
        SkillTools.objects.bulk_update(tools, ["team"])
        LLMSkill.objects.filter(is_template=True).delete()
        skill_list = [LLMSkill(**skill) for skill in SKILL_LIST]
        LLMSkill.objects.bulk_create(skill_list, batch_size=10)
