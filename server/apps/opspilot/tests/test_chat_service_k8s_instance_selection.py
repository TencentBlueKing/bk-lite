from apps.opspilot.services.chat_service import ChatService


def test_single_k8s_instance_sets_default_instance_name(mocker):
    llm_model = mocker.Mock()
    llm_model.openai_api_base = "https://example.com/v1"
    llm_model.openai_api_key = "key"
    llm_model.model_name = "gpt-4o"
    llm_model.protocol_type = "openai"

    mocker.patch("apps.opspilot.services.history_service.history_service.process_user_message_and_images", return_value=("检查所有工作负载有没有问题", []))
    mocker.patch("apps.opspilot.services.history_service.history_service.process_chat_history", return_value=[])
    mocker.patch("apps.opspilot.services.chat_service.resolve_skill_params", return_value="system")

    skill_tool = mocker.Mock()
    skill_tool.id = 1
    skill_tool.name = "kubernetes_data_collection"
    skill_tool.is_build_in = False
    skill_tool.params = {"name": "kubernetes_data_collection"}
    mocker.patch("apps.opspilot.services.chat_service.SkillTools.objects.filter", return_value=[skill_tool])

    kwargs = {
        "user_message": "检查所有工作负载有没有问题",
        "chat_history": [],
        "skill_prompt": "system",
        "skill_params": [],
        "temperature": 0.1,
        "user_id": 1,
        "enable_rag": False,
        "enable_rag_knowledge_source": False,
        "skill_type": 1,
        "entry_type": "nats",
        "locale": "zh-Hans",
        "tools": [
            {
                "id": 1,
                "name": "kubernetes_data_collection",
                "kwargs": [
                    {
                        "key": "kubernetes_instances",
                        "value": '[{"id":"k8s-1","name":"Kubernetes - 1","kubeconfig_data":"apiVersion: v1"}]',
                        "type": "array",
                    }
                ],
            }
        ],
    }

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(kwargs, llm_model)

    assert chat_kwargs["extra_config"]["instance_name"] == "Kubernetes - 1"
    assert chat_kwargs["extra_config"]["instance_id"] == "k8s-1"
    assert chat_kwargs["extra_config"]["entry_type"] == "nats"
    assert "_multi_instance_options" not in chat_kwargs["extra_config"]


def test_multiple_k8s_instances_requires_real_instance_choice_without_all_option(mocker):
    llm_model = mocker.Mock()
    llm_model.openai_api_base = "https://example.com/v1"
    llm_model.openai_api_key = "key"
    llm_model.model_name = "gpt-4o"
    llm_model.protocol_type = "openai"

    mocker.patch(
        "apps.opspilot.services.history_service.history_service.process_user_message_and_images", return_value=("查看下k8s集群所有工作负载的配置有没有问题", [])
    )
    mocker.patch("apps.opspilot.services.history_service.history_service.process_chat_history", return_value=[])
    mocker.patch("apps.opspilot.services.chat_service.resolve_skill_params", return_value="system")

    skill_tool = mocker.Mock()
    skill_tool.id = 1
    skill_tool.name = "kubernetes_data_collection"
    skill_tool.is_build_in = False
    skill_tool.params = {"name": "kubernetes_data_collection"}
    mocker.patch("apps.opspilot.services.chat_service.SkillTools.objects.filter", return_value=[skill_tool])

    kwargs = {
        "user_message": "查看下k8s集群所有工作负载的配置有没有问题",
        "chat_history": [],
        "skill_prompt": "system",
        "skill_params": [],
        "temperature": 0.1,
        "user_id": 1,
        "enable_rag": False,
        "enable_rag_knowledge_source": False,
        "skill_type": 1,
        "locale": "zh-Hans",
        "tools": [
            {
                "id": 1,
                "name": "kubernetes_data_collection",
                "kwargs": [
                    {
                        "key": "kubernetes_instances",
                        "value": (
                            '[{"id":"k8s-1","name":"Kubernetes - 1","kubeconfig_data":"apiVersion: v1"},'
                            '{"id":"k8s-2","name":"Kubernetes - 2","kubeconfig_data":"apiVersion: v1"}]'
                        ),
                        "type": "array",
                    }
                ],
            }
        ],
    }

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(kwargs, llm_model)

    assert "instance_name" not in chat_kwargs["extra_config"]
    assert chat_kwargs["extra_config"]["_multi_instance_options"] == ["Kubernetes - 1", "Kubernetes - 2"]

    prompt = chat_kwargs["tools_servers"][0]["extra_tools_prompt"]
    assert "必须先调用 request_user_choice" in prompt
    assert "不需要让用户选" not in prompt
    assert "对全部集群执行" not in prompt


def test_current_turn_images_go_to_extra_config_not_blank_history(mocker):
    llm_model = mocker.Mock()
    llm_model.openai_api_base = "https://example.com/v1"
    llm_model.openai_api_key = "key"
    llm_model.model_name = "gpt-4o"
    llm_model.protocol_type = "openai"
    llm_model.vendor = None
    llm_model.vendor_id = None

    mocker.patch("apps.opspilot.services.chat_service.resolve_skill_params", return_value="system")
    mocker.patch("apps.opspilot.services.chat_service.SkillTools.objects.filter", return_value=[])

    kwargs = {
        "user_message": [
            {"type": "image_url", "image_url": "data:image/png;base64,abc"},
            {"type": "message", "message": "介绍下网络吞吐趋势"},
        ],
        "chat_history": [{"event": "user", "message": "上一问"}, {"event": "bot", "message": "上一答"}],
        "skill_prompt": "system",
        "skill_params": [],
        "temperature": 0.1,
        "user_id": 1,
        "enable_rag": False,
        "enable_rag_knowledge_source": False,
        "skill_type": 1,
        "locale": "zh-Hans",
        "tools": [],
        "conversation_window_size": 10,
    }

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(kwargs, llm_model)

    assert chat_kwargs["user_message"] == "介绍下网络吞吐趋势"
    assert chat_kwargs["extra_config"]["current_image_data"] == ["data:image/png;base64,abc"]
    assert chat_kwargs["chat_history"] == [
        {"event": "user", "message": "上一问"},
        {"event": "bot", "message": "上一答"},
    ]
    assert all(item.get("message") != "" for item in chat_kwargs["chat_history"])
