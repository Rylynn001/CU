"""长任务计划的输入边界；步骤按依赖顺序排列，不能引用未来步骤。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerationStep(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)
    media_type: Literal['image', 'video']
    prompt: str = Field(min_length=1, max_length=12000)
    depends_on: list[str] = Field(default_factory=list, max_length=12)
    input_asset_ids: list[int] = Field(default_factory=list, max_length=10)
    duration: int | None = Field(default=None, ge=1, le=60)


class GenerationPlan(BaseModel):
    steps: list[GenerationStep] = Field(min_length=2, max_length=12)

    @model_validator(mode='after')
    def check_dependencies(self):
        previous = {}
        for step in self.steps:
            if step.id in previous or any(key not in previous for key in step.depends_on):
                raise ValueError('步骤编号不能重复，依赖必须指向前面的步骤')
            if len(set(step.depends_on)) != len(step.depends_on):
                raise ValueError('步骤依赖不能重复')
            if step.media_type == 'image' and any(previous[key] != 'image' for key in step.depends_on):
                raise ValueError('图片步骤不能参考视频输出')
            if not step.prompt.strip():
                raise ValueError('步骤描述不能为空')
            previous[step.id] = step.media_type
        return self
