# API 迁移检查清单

## 一、前端调用的接口汇总

### 1. 认证模块
| 路径 | 方法 | ComfyUI | Background | 状态 |
|------|------|---------|------------|------|
| `/auth/login` | POST | ✅ | ✅ | ✅ 正常 |
| `/auth/verify` | GET | ✅ | ✅ | 待验证 |

### 2. 配置与模型管理
| 路径 | 方法 | ComfyUI | Background | 状态 |
|------|------|---------|------------|------|
| `/api-proxy/config` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/config` | PUT | ✅ | ❌ | 缺失 |
| `/api-proxy/models` | GET | ✅ | ✅ | 待验证参数 |
| `/api-proxy/models` | POST | ✅ | ❌ | 缺失 |
| `/api-proxy/models/{model_id}` | DELETE | ✅ | ❌ | 缺失 |
| `/api-proxy/providers` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/providers/{provider_id}/models` | GET | ✅ | ✅ | 待验证 |

### 3. 资产管理
| 路径 | 方法 | ComfyUI | Background | 状态 |
|------|------|---------|------------|------|
| `/api-proxy/user/assets` | GET | ✅ | ✅ | 待验证返回格式 |
| `/api-proxy/user/assets/{asset_id}/favorite` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/upload/file` | POST | ✅ | ✅ | 待验证返回格式 |
| `/api-proxy/upload/image/{asset_id}/b64` | GET | ✅ | ❌ | 缺失 |
| `/api-proxy/assets/by-ids` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/extract-frame` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/output/{filename}` | GET | ✅ | ✅ | 待验证 |

### 4. 历史记录
| 路径 | 方法 | ComfyUI | Background | 状态 |
|------|------|---------|------------|------|
| `/api-proxy/history` | GET | ✅ | ✅ | 待验证分页 |
| `/api-proxy/history` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/history` | DELETE | ✅ | ✅ | 待验证 |
| `/api-proxy/history/{history_id}` | DELETE | ✅ | ✅ | 待验证 |
| `/api-proxy/history/{history_id}/retry` | POST | ✅ | ❌ | 缺失 |
| `/api-proxy/history/by-asset/{asset_id}` | GET | ✅ | ✅ | 待验证 |

### 5. 图片/视频生成
| 路径 | 方法 | ComfyUI | Background | 状态 |
|------|------|---------|------------|------|
| `/api-proxy/txt2img` | POST | ✅ | ❌ | 缺失 |
| `/api-proxy/txt2video` | POST | ✅ | ❌ | 缺失 |
| `/api-proxy/img2video` | POST | ✅ | ❌ | 缺失 |
| `/api-proxy/task/{task_id}` | GET | ✅ | ❌ | 路径不同 |
| `/api-proxy/task/{task_id}/cancel` | POST | ✅ | ❌ | 缺失 |
| `/api-proxy/task/{task_id}/priority` | POST | ✅ | ❌ | 缺失 |

### 6. 项目与分类管理
| 路径 | 方法 | ComfyUI | Background | 状态 |
|------|------|---------|------------|------|
| `/api-proxy/projects` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/projects` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/projects/{project_id}` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/projects/{project_id}` | PUT | ✅ | ✅ | 待验证 |
| `/api-proxy/projects/{project_id}` | DELETE | ✅ | ✅ | 待验证 |
| `/api-proxy/projects/{project_id}/categories` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/categories` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/categories/{category_id}` | PUT | ✅ | ✅ | 待验证 |
| `/api-proxy/categories/{category_id}` | DELETE | ✅ | ✅ | 待验证 |
| `/api-proxy/categories/{category_id}/assets` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/categories/{category_id}/assets` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/categories/{category_id}/assets/{asset_id}` | DELETE | ✅ | ✅ | 待验证 |

### 7. 团队协作
| 路径 | 方法 | ComfyUI | Background | 状态 |
|------|------|---------|------------|------|
| `/api-proxy/projects/{project_id}/members` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/projects/{project_id}/members` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/projects/{project_id}/members/{member_user_id}` | PUT | ✅ | ✅ | 待验证 |
| `/api-proxy/projects/{project_id}/members/{member_user_id}` | DELETE | ✅ | ✅ | 待验证 |
| `/api-proxy/projects/{project_id}/candidate-users` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/pending-assets` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/my-submissions` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/categories/{category_id}/assets/{asset_id}/review` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/categories/{category_id}/assets/{asset_id}/reviews` | GET | ✅ | ✅ | 待验证 |

### 8. 节点面板
| 路径 | 方法 | ComfyUI | Background | 状态 |
|------|------|---------|------------|------|
| `/api-proxy/node-boards` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/node-boards` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/node-boards/{board_id}` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/node-boards/{board_id}` | PUT | ✅ | ✅ | 待验证 |
| `/api-proxy/node-boards/{board_id}` | PATCH | ✅ | ❌ | 缺失 |
| `/api-proxy/node-boards/{board_id}` | DELETE | ✅ | ✅ | 待验证 |

### 9. Gecko 相关
| 路径 | 方法 | ComfyUI | Background | 状态 |
|------|------|---------|------------|------|
| `/api-proxy/gecko/init` | POST | ✅ | ❌ | 完全缺失 |
| `/api-proxy/gecko/tasks` | POST | ✅ | ❌ | 完全缺失 |
| `/api-proxy/gecko/tasks` | GET | ✅ | ❌ | 完全缺失 |
| `/api-proxy/gecko/task-directories` | GET | ✅ | ❌ | 完全缺失 |
| `/api-proxy/gecko/upload-media` | POST | ✅ | ❌ | 完全缺失 |
| `/api-proxy/gecko/daily-login` | POST | ✅ | ❌ | 完全缺失 |

### 10. 短剧管理
| 路径 | 方法 | ComfyUI | Background | 状态 |
|------|------|---------|------------|------|
| `/api-proxy/dramas` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/dramas` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/dramas/{drama_id}` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/dramas/{drama_id}` | PUT | ✅ | ✅ | 待验证 |
| `/api-proxy/dramas/{drama_id}` | DELETE | ✅ | ✅ | 待验证 |
| `/api-proxy/episodes` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/episodes/{episode_id}` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/episodes/{episode_id}` | PUT | ✅ | ✅ | 待验证 |
| `/api-proxy/episodes/{episode_id}` | DELETE | ✅ | ✅ | 待验证 |
| `/api-proxy/episodes/{episode_id}/characters` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/episodes/{episode_id}/scenes` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/episodes/{episode_id}/storyboards` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/episodes/{episode_id}/storyboards` | POST | ✅ | ✅ | 待验证 |
| `/api-proxy/storyboards/{storyboard_id}` | PUT | ✅ | ✅ | 待验证 |
| `/api-proxy/storyboards/{storyboard_id}` | DELETE | ✅ | ✅ | 待验证 |
| `/api-proxy/timbres` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/characters/{character_id}` | PUT | ✅ | ✅ | 待验证 |
| `/api-proxy/characters/{character_id}/image` | PUT | ✅ | ✅ | 待验证 |
| `/api-proxy/scenes/{scene_id}/image` | PUT | ✅ | ✅ | 待验证 |
| `/api-proxy/voice/{filename}` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/dramas/{drama_id}/episodes/{episode_number}` | GET | ✅ | ✅ | 待验证 |
| `/api-proxy/characters/{character_id}/generate-voice-sample` | POST | ✅ | ❌ | 缺失 |
| `/api-proxy/storyboards/{storyboard_id}/generate-tts` | POST | ✅ | ❌ | 缺失 |
| `/api-proxy/storyboards/{storyboard_id}/compose` | POST | ✅ | ❌ | 缺失 |
| `/api-proxy/episodes/{episode_id}/merge` | POST | ✅ | ❌ | 缺失 |

## 二、缺失接口优先级

### 🔴 高优先级（图片视频生成核心）
1. `/api-proxy/txt2img` - 文生图
2. `/api-proxy/txt2video` - 文生视频
3. `/api-proxy/img2video` - 图生视频
4. `/api-proxy/task/{task_id}` - 任务状态查询
5. `/api-proxy/task/{task_id}/cancel` - 取消任务
6. `/api-proxy/task/{task_id}/priority` - 任务插队

### 🟡 中优先级（完整功能）
7. `/api-proxy/history/{history_id}/retry` - 重试历史记录
8. `/api-proxy/upload/image/{asset_id}/b64` - 获取 base64 图片
9. `/api-proxy/config` PUT - 保存配置
10. `/api-proxy/models` POST/DELETE - 模型管理
11. `/api-proxy/node-boards/{board_id}` PATCH - 部分更新工作区

### 🟢 低优先级（Gecko 模块）
12. Gecko 相关所有接口（6个）

### 🔵 待定（短剧特效）
13. 短剧语音合成相关（4个）

## 三、已完成的接口迁移

### ✅ 已补充的核心接口

1. **图片视频生成模块** (`background/api/generation.py`)
   - ✅ POST `/api-proxy/txt2img` - 文生图
   - ✅ POST `/api-proxy/txt2video` - 文生视频
   - ✅ POST `/api-proxy/img2video` - 图生视频
   - ✅ GET `/api-proxy/task/{task_id}` - 查询任务状态
   - ✅ POST `/api-proxy/task/{task_id}/cancel` - 取消任务
   - ✅ POST `/api-proxy/task/{task_id}/priority` - 任务插队

2. **历史记录模块** (`background/api/history.py`)
   - ✅ POST `/api-proxy/history/{history_id}/retry` - 重试失败记录

3. **配置与模型管理** (`background/api/providers.py`)
   - ✅ PUT `/api-proxy/config` - 保存 API 配置
   - ✅ POST `/api-proxy/models` - 新增模型
   - ✅ DELETE `/api-proxy/models/{model_id}` - 删除模型

4. **工作区管理** (`background/api/node_boards.py`)
   - ✅ PATCH `/api-proxy/node-boards/{board_id}` - 重命名工作区

### 🔴 仍然缺失的接口

1. **Gecko 模块** (完全缺失，需要整个模块迁移)
   - ❌ POST `/api-proxy/gecko/init` - Gecko 初始化
   - ❌ POST `/api-proxy/gecko/tasks` - 获取任务列表
   - ❌ POST `/api-proxy/gecko/task-directories` - 获取任务目录
   - ❌ POST `/api-proxy/gecko/upload-media` - 上传媒体
   - ❌ POST `/api-proxy/gecko/daily-login` - 每日签到

2. **短剧特效功能** (需要依赖外部服务)
   - ❌ POST `/api-proxy/characters/{character_id}/generate-voice-sample` - 生成角色语音
   - ❌ POST `/api-proxy/storyboards/{storyboard_id}/generate-tts` - 生成配音
   - ❌ POST `/api-proxy/storyboards/{storyboard_id}/compose` - 合成分镜视频
   - ❌ POST `/api-proxy/episodes/{episode_id}/merge` - 合并剧集视频

3. **资产管理** (待确认前端是否真的使用)
   - ❓ GET `/api-proxy/upload/image/{asset_id}/b64` - 获取 base64 图片
