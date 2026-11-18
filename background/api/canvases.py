"""独立画布接口，不读取或写入画布文件。"""
import json
import math
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from api.auth import get_current_user
from repositories import canvas_repo
from repositories.workflow_repo import WorkflowRepository
from agents.services.canvas_tasks import submit_generation, refresh_tasks, apply_tasks

router = APIRouter()


class CanvasDocument(BaseModel):
    version: Literal[1] = 1
    nodes: list[dict] = Field(default_factory=list, max_length=2000)
    edges: list[dict] = Field(default_factory=list, max_length=10000)
    viewport: dict = Field(default_factory=lambda: {'x': 0, 'y': 0, 'zoom': 1})

    @model_validator(mode='after')
    def validate_graph(self):
        ids = set()
        for node in self.nodes:
            node_id = node.get('id')
            if not isinstance(node_id, str) or not node_id or node_id in ids:
                raise ValueError('节点 ID 必须唯一且非空')
            ids.add(node_id)
            if not isinstance(node.get('type'), str) or not isinstance(node.get('data'), dict):
                raise ValueError('节点缺少组件类型或数据')
            position = node.get('position', {})
            if not isinstance(position, dict) or not all(
                isinstance(position.get(key), (int, float)) and math.isfinite(position[key]) for key in ('x', 'y')
            ):
                raise ValueError('节点位置无效')
        edge_ids = set()
        for edge in self.edges:
            edge_id = edge.get('id')
            if not isinstance(edge_id, str) or not edge_id or edge_id in edge_ids:
                raise ValueError('连线 ID 必须唯一且非空')
            edge_ids.add(edge_id)
            if not isinstance(edge.get('source'), str) or not isinstance(edge.get('target'), str) or edge['source'] not in ids or edge['target'] not in ids:
                raise ValueError('连线引用的节点不存在')
        if not all(isinstance(self.viewport.get(k), (int, float)) and math.isfinite(self.viewport[k]) for k in ('x', 'y', 'zoom')) or self.viewport['zoom'] <= 0:
            raise ValueError('视口无效')
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode('utf-8')) > 8 * 1024 * 1024:
            raise ValueError('画布文档不能超过 8 MB')
        return self


class CanvasCreate(BaseModel):
    name: str = Field(default='新画布', max_length=100)


class CanvasRename(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CanvasSave(CanvasCreate):
    document: CanvasDocument
    base_node_ids: list[str] = Field(default_factory=list, max_length=2000)


class CanvasGeneration(BaseModel):
    prompt: str = Field(min_length=1)
    model: int
    parameters: dict = Field(default_factory=dict)
    input_asset_ids: list[int] = Field(default_factory=list, max_length=20)


def serialize(row):
    if row.get('updated_at'):
        row['updated_at'] = int(row['updated_at'].timestamp() * 1000)
    if isinstance(row.get('document'), str):
        row['document'] = json.loads(row['document'])
    return row


def require_canvas(canvas_id, user):
    row = canvas_repo.get_canvas(canvas_id, user['user_id'])
    if not row:
        raise HTTPException(404, '画布不存在')
    return row


@router.get('/canvases')
def list_canvases(user: dict = Depends(get_current_user)):
    return {'canvases': [serialize(row) for row in canvas_repo.list_canvases(user['user_id'])]}


@router.post('/canvases')
def create_canvas(req: CanvasCreate, user: dict = Depends(get_current_user)):
    canvas_id = canvas_repo.create_canvas(user['user_id'], req.name.strip() or '新画布', CanvasDocument().model_dump())
    return serialize(require_canvas(canvas_id, user))


@router.get('/canvases/tasks/{history_id}')
def get_canvas_task(history_id: int, user: dict = Depends(get_current_user)):
    task = canvas_repo.get_history_task(history_id, user['user_id'])
    if not task:
        raise HTTPException(404, '生成记录不存在')
    return task


@router.get('/canvases/{canvas_id}')
def get_canvas(canvas_id: int, user: dict = Depends(get_current_user)):
    row = serialize(require_canvas(canvas_id, user))
    tasks = refresh_tasks(WorkflowRepository.get_canvas_executions(canvas_id, user['user_id']), user['user_id'])
    row['document'] = apply_tasks(row['document'], tasks)
    return row


@router.put('/canvases/{canvas_id}')
def save_canvas(canvas_id: int, req: CanvasSave, user: dict = Depends(get_current_user)):
    require_canvas(canvas_id, user)
    document = canvas_repo.save_canvas(canvas_id, user['user_id'], req.name.strip() or '新画布', req.document.model_dump(), req.base_node_ids)
    tasks = refresh_tasks(WorkflowRepository.get_canvas_executions(canvas_id, user['user_id']), user['user_id'])
    return {'success': True, 'document': apply_tasks(document, tasks)}


@router.patch('/canvases/{canvas_id}')
def rename_canvas(canvas_id: int, req: CanvasRename, user: dict = Depends(get_current_user)):
    require_canvas(canvas_id, user)
    name = req.name.strip()
    if not name:
        raise HTTPException(400, '请输入画布名称')
    canvas_repo.rename_canvas(canvas_id, user['user_id'], name)
    return {'success': True}


@router.post('/canvases/{canvas_id}/nodes/{node_id}/generate')
async def generate_node(canvas_id: int, node_id: str, req: CanvasGeneration, user: dict = Depends(get_current_user)):
    row = serialize(require_canvas(canvas_id, user))
    node = next((node for node in row['document']['nodes'] if node['id'] == node_id), None)
    if not node or node['type'] not in ('remote-imageGenerationNode', 'remote-videoGenerationNode'):
        raise HTTPException(404, '生成节点不存在')
    try:
        return await submit_generation(user, canvas_id, 'video' if node['type'] == 'remote-videoGenerationNode' else 'image', req.model_dump(), node_id=node_id)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.delete('/canvases/{canvas_id}')
def delete_canvas(canvas_id: int, user: dict = Depends(get_current_user)):
    require_canvas(canvas_id, user)
    canvas_repo.delete_canvas(canvas_id, user['user_id'])
    return {'success': True}
