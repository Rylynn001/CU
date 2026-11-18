"""提示词输出校验：结构化状态负责分流，文本检查拦截明显放错字段的对话。

这里不尝试用关键词理解整段创作内容，也不把问号当作错误。
只检查最终提示词中的明显对话语句；语义不确定时仍由优化模型澄清。
"""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


def unquoted_text(text: str) -> str:
    """排除角色台词等引用内容，避免把“你想要什么？”误判成向用户追问。"""
    return re.sub(r'“[^”]*”|「[^」]*」|『[^』]*』|"[^"\n]*"|\'[^\'\n]*\'', '', text)


def validate_final_prompt(value: str | None) -> str:
    """返回干净的最终提示词；明显的反问、确认语和空回复必须重新生成。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('最终提示词不能为空')
    text = value.strip()
    plain = unquoted_text(text)
    # 整个输出只有一句带引号的问题时，仍需检查；排除台词必须有画面上下文。
    if not plain.strip():
        plain = text.strip('“”「」『』"\'')
    # 只匹配句首/行首的对话形式，不禁止提示词中的角色问句、标点或普通模型描述。
    question = re.search(
        r'(?:^|[\n。！？!?])\s*(?:[-*]\s*)?'
        r'(?:请问|请(?:您|你)?(?:先)?(?:提供|补充|确认|选择|告诉|上传|说明)'
        r'|(?:您|你)(?:想要|希望|需要|想|要)'
        r'|(?:要|想要|需要)?(?:优化|使用|选择|采用|生成|制作)?(?:哪(?:个|种|些)|什么|多长|多少|几秒))',
        plain,
    )
    if question or re.match(r'^(?:好的|当然可以|没问题|我可以帮|请确认|是否需要)', plain):
        raise ValueError('最终提示词中包含面向用户的追问或对话回复')
    return text


class PromptEnhancementResult(BaseModel):
    """生成链路的唯一返回协议；文字问题与最终提示词不能同时出现。"""
    model_config = ConfigDict(extra='forbid')
    status: Literal['ready', 'needs_clarification']
    prompt: str | None = None
    reply: str | None = None
    clarification_type: Literal['content', 'reference', 'generation_parameters'] | None = None

    @model_validator(mode='after')
    def check_content(self):
        if self.status == 'ready':
            if self.reply is not None or self.clarification_type is not None:
                raise ValueError('ready 只能填写 prompt，不能同时追问用户')
            self.prompt = validate_final_prompt(self.prompt)
        else:
            if self.prompt is not None or not isinstance(self.reply, str) or not self.reply.strip():
                raise ValueError('追问只能填写非空 reply，不能填写 prompt')
            if self.clarification_type is None:
                raise ValueError('追问必须说明缺少的是创作内容还是参考素材')
            # 模型、比例、时长等由后续参数面板选择，不能因此中断提示词优化。
            # 同时检查实际问句，避免模型把参数问题错误标注为 content。
            if self.clarification_type == 'generation_parameters' or re.search(
                r'生成模型|哪个模型|哪种模型|什么模型|模型的提示词|模型(?:版本|编号|选|用)'
                r'|版本|平台|比例|分辨率|画幅|时长|质量|张数', unquoted_text(self.reply),
            ):
                raise ValueError('生成参数由后续面板确认，不应向用户询问生成参数')
            self.reply = self.reply.strip()
        return self
