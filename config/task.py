"""任务配置模块——类似 maa-cli 的任务配置"""
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Task:
    """单个任务配置"""
    name: str
    task_type: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(
            name=data.get("name", data.get("type", "")),
            task_type=data.get("type", ""),
            params=data.get("params", {}),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.task_type,
            "params": self.params,
        }


@dataclass
class TaskConfig:
    """任务列表配置"""
    client_type: str = "Official"
    start_game_enabled: bool = False
    close_game_enabled: bool = False
    tasks: list[Task] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "TaskConfig":
        tasks = [Task.from_dict(t) for t in data.get("tasks", [])]
        return cls(
            client_type=data.get("client_type", "Official"),
            start_game_enabled=data.get("start_game_enabled", False),
            close_game_enabled=data.get("close_game_enabled", False),
            tasks=tasks,
        )

    @classmethod
    def from_file(cls, path: pathlib.Path | str) -> Optional["TaskConfig"]:
        path = pathlib.Path(path)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                if path.suffix == ".json":
                    data = json.load(f)
                else:
                    # 暂时只支持 JSON，之后可以加 TOML/YAML
                    return None
            return cls.from_dict(data)
        except Exception as e:
            print(f"加载任务配置失败: {e}")
            return None

    def to_dict(self) -> dict:
        return {
            "client_type": self.client_type,
            "start_game_enabled": self.start_game_enabled,
            "close_game_enabled": self.close_game_enabled,
            "tasks": [t.to_dict() for t in self.tasks],
        }


def create_default_tasks() -> TaskConfig:
    """创建默认任务配置——类似 MAA 的日常任务"""
    return TaskConfig(
        client_type="Official",
        start_game_enabled=False,
        close_game_enabled=False,
        tasks=[
            Task(name="启动", task_type="StartUp", params={"client_type": "Official", "start_game_enabled": False}),
            Task(name="基建", task_type="Infrast", params={"mode": 10000, "facility": ["Trade", "Dorm", "Control", "Reception", "Office", "Mfg", "Power"]}),
            Task(name="打副本", task_type="Fight", params={"stage": "1-7", "medicine": 0, "expiring_medicine": 0, "report_to_penguin": False, "client_type": "Official"}),
            Task(name="访问好友", task_type="Visit"),
            Task(name="收邮件", task_type="Mall"),
            Task(name="基建收工", task_type="Infrast", params={"mode": 0}),
        ],
    )
