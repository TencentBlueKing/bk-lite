from apps.core.logger import cmdb_logger as logger


class CollectionPluginRegistry:
    _registry = {}
    _initialized = False

    @classmethod
    def ensure_initialized(cls):
        if cls._initialized:
            return
        from apps.cmdb.collection.plugins.loader import CollectionPluginLoader

        cls._initialized = CollectionPluginLoader.load_plugins()

    @classmethod
    def register(cls, plugin_cls):
        task_type = getattr(plugin_cls, "supported_task_type", None)
        model_id = getattr(plugin_cls, "supported_model_id", None)
        if not task_type or not model_id:
            return

        task_plugins = cls._registry.setdefault(task_type, {})
        current_cls = task_plugins.get(model_id)
        if current_cls is None:
            task_plugins[model_id] = plugin_cls
            return

        current_priority = getattr(current_cls, "priority", 0)
        new_priority = getattr(plugin_cls, "priority", 0)

        if new_priority > current_priority:
            logger.info(
                "Collection plugin overridden: task_type=%s, model_id=%s, old=%s, new=%s",
                task_type,
                model_id,
                current_cls.__name__,
                plugin_cls.__name__,
            )
            task_plugins[model_id] = plugin_cls
            return

        if new_priority == current_priority:
            logger.error(
                "Collection plugin conflict: task_type=%s, model_id=%s, current=%s, new=%s",
                task_type,
                model_id,
                current_cls.__name__,
                plugin_cls.__name__,
            )

    @classmethod
    def get_plugin(cls, task_type: str, model_id: str):
        cls.ensure_initialized()
        task_plugins = cls._registry.get(task_type, {})
        plugin_cls = task_plugins.get(model_id) or task_plugins.get("*")
        if plugin_cls is None:
            raise ValueError(f"Unsupported collection plugin: task_type={task_type}, model_id={model_id}")
        return plugin_cls

    @classmethod
    def get_registry_snapshot(cls):
        cls.ensure_initialized()
        snapshot = []
        for task_type in sorted(cls._registry):
            for model_id in sorted(cls._registry[task_type]):
                plugin_cls = cls._registry[task_type][model_id]
                snapshot.append(
                    {
                        "task_type": task_type,
                        "model_id": model_id,
                        "class_name": plugin_cls.__name__,
                        "module": plugin_cls.__module__,
                        "plugin_source": getattr(plugin_cls, "plugin_source", "unknown"),
                        "priority": getattr(plugin_cls, "priority", 0),
                    }
                )
        return snapshot
