from __future__ import annotations

from aiohttp import web

from typing import TYPE_CHECKING, TypedDict
if TYPE_CHECKING:
    from comfy_api.latest._io_public import NodeReplace

from comfy_execution.graph_utils import is_link
import nodes

class NodeStruct(TypedDict):
    inputs: dict[str, str | int | float | bool | tuple[str, int]]
    class_type: str
    _meta: dict[str, str]

def copy_node_struct(node_struct: NodeStruct, empty_inputs: bool = False) -> NodeStruct:
    new_node_struct = node_struct.copy()
    if empty_inputs:
        new_node_struct["inputs"] = {}
    else:
        new_node_struct["inputs"] = node_struct["inputs"].copy()
    new_node_struct["_meta"] = node_struct["_meta"].copy()
    return new_node_struct


class NodeReplaceManager:
    """Manages node replacement registrations."""

    def __init__(self):
        self._replacements: dict[str, list[NodeReplace]] = {}

    def register(self, node_replace: NodeReplace):
        """Register a node replacement mapping."""
        self._replacements.setdefault(node_replace.old_node_id, []).append(node_replace)

    def get_replacement(self, old_node_id: str) -> list[NodeReplace] | None:
        """Get replacements for an old node ID."""
        return self._replacements.get(old_node_id)

    def has_replacement(self, old_node_id: str) -> bool:
        """Check if a replacement exists for an old node ID."""
        return old_node_id in self._replacements

    def apply_replacements(self, prompt: dict[str, NodeStruct]):
        # connections: 记录每个节点的输出被哪些节点连接
        # 结构：{ 被连接的节点编号: [(连接方节点编号, 连接方输入名, 输出槽索引), ...] }
        connections: dict[str, list[tuple[str, str, int]]] = {}

        # need_replacement: 需要被替换的节点编号集合
        need_replacement: set[str] = set()

        # ── 第一步：扫描所有节点，找出需要替换的节点，并建立连接关系表 ──
        for node_number, node_struct in prompt.items():
            # 跳过格式不完整的节点
            if "class_type" not in node_struct or "inputs" not in node_struct:
                continue
            class_type = node_struct["class_type"]

            # 如果这个节点类型在 ComfyUI 注册表中不存在，但有注册替换规则，则标记为需要替换
            if class_type not in nodes.NODE_CLASS_MAPPINGS.keys() and self.has_replacement(class_type):
                need_replacement.add(node_number)

            # 遍历该节点所有输入，找出其中是"连接"类型的（即从其他节点输出槽引用的值）
            for input_id, input_value in node_struct["inputs"].items():
                if is_link(input_value):
                    # input_value 格式：[来源节点编号, 来源节点输出槽索引]
                    conn_number = input_value[0]
                    # 在 connections 中记录：conn_number 这个节点的输出，被当前节点的 input_id 输入槽引用
                    connections.setdefault(conn_number, []).append((node_number, input_id, input_value[1]))
            arr = []
            arr.sort()
        # ── 第二步：对所有需要替换的节点逐个执行替换 ──
        for node_number in need_replacement:
            node_struct = prompt[node_number]
            class_type = node_struct["class_type"]
            replacements = self.get_replacement(class_type)
            if replacements is None:
                continue
            # 如果有多条替换规则，只取第一条
            replacement = replacements[0]
            new_node_id = replacement.new_node_id

            # 如果替换目标节点类型也不在注册表中，跳过（避免无效替换）
            if new_node_id not in nodes.NODE_CLASS_MAPPINGS.keys():
                continue

            # ── 替换第一步：替换节点类型（class_type）──
            # 创建一个空 inputs 的新节点结构，class_type 改为新节点 ID
            new_node_struct = copy_node_struct(node_struct, empty_inputs=True)
            new_node_struct["class_type"] = new_node_id

            # ── 替换第二步：替换输入参数 ──
            if replacement.input_mapping is not None:
                for input_map in replacement.input_mapping:
                    if "set_value" in input_map:
                        # 直接写死一个固定值
                        new_node_struct["inputs"][input_map["new_id"]] = input_map["set_value"]
                    elif "old_id" in input_map:
                        # 从旧节点的同名（或重命名）输入中复制值
                        new_node_struct["inputs"][input_map["new_id"]] = node_struct["inputs"][input_map["old_id"]]

            # 将修改后的新节点结构写回 prompt
            prompt[node_number] = new_node_struct

            # ── 替换第三步：替换输出槽索引 ──
            # 如果新节点的输出槽位置和旧节点不同，需要修改所有接收这个节点输出的地方
            if replacement.output_mapping is not None:
                if node_number in connections:
                    # 遍历所有接收当前节点输出的下游节点
                    for conns in connections[node_number]:
                        conn_node_number, conn_input_id, old_output_idx = conns
                        # 找到匹配的输出槽映射规则
                        for output_map in replacement.output_mapping:
                            if output_map["old_idx"] == old_output_idx:
                                new_output_idx = output_map["new_idx"]
                                # 直接修改下游节点的输入引用，将旧输出槽索引改为新的
                                previous_input = prompt[conn_node_number]["inputs"][conn_input_id]
                                previous_input[1] = new_output_idx

    def as_dict(self):
        """Serialize all replacements to dict."""
        return {
            k: [v.as_dict() for v in v_list]
            for k, v_list in self._replacements.items()
        }

    def add_routes(self, routes):
        @routes.get("/node_replacements")
        async def get_node_replacements(request):
            return web.json_response(self.as_dict())
