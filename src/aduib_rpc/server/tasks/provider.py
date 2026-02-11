from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from aduib_rpc.server.tasks.task_manager import TaskManager

logger = logging.getLogger(__name__)


def task_manager_provider(name: str):
    """Decorator to register a task manager provider class."""

    def decorator(cls: Any) -> Any:
        if not name:
            raise ValueError("Task manager provider name must be provided")
        TaskManagerProvider.register_task_source_class(name, cls)
        logger.info(f"Task manager provider {name} registered")
        return cls

    return decorator


class TaskManagerProvider:
    """Task manager provider for managing task sources."""

    task_source_classes: dict[str, Any] = {}
    task_source_instances: dict[str, TaskManager] = {}

    @classmethod
    def register_task_source_class(cls, source_type: str, source_class: Any) -> None:
        """Register a task source class."""
        cls.task_source_classes[source_type] = source_class

    @classmethod
    def get_task_source_class(cls, source_type: str) -> Any | None:
        """Get a registered task source class."""
        return cls.task_source_classes.get(source_type)

    @classmethod
    def from_task_source_instance(cls, source_type: str, **kwargs) -> TaskManager | None:
        """Create and register a task source instance."""
        source_class = cls.get_task_source_class(source_type)
        if source_class is None:
            logger.warning("No task source class registered for %s", source_type)
            raise ValueError(f"No task source class registered for {source_type}")
        instance = source_class(**kwargs)
        cls.task_source_instances[source_type] = instance
        return instance

    @classmethod
    def get_task_source_instance(cls, source_type: str) -> TaskManager | None:
        """Get a registered task source instance."""
        return cls.task_source_instances.get(source_type)
