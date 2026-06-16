-- 火爆剧集生成系统 — MySQL 建表脚本
-- 字符集统一用 utf8mb4

CREATE TABLE dramas (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '剧集 ID',
    title           VARCHAR(255) NOT NULL           COMMENT '剧集标题',
    description     TEXT                            COMMENT '剧集简介',
    genre           VARCHAR(100)                    COMMENT '剧集类型，如 爱情/古装/悬疑',
    style           VARCHAR(100) DEFAULT 'realistic' COMMENT '视觉风格，如 realistic/anime',
    total_episodes  INT DEFAULT 1                   COMMENT '总集数',
    total_duration  INT DEFAULT 0                   COMMENT '总时长（秒）',
    status          VARCHAR(50) NOT NULL DEFAULT 'draft' COMMENT '状态：draft/published/archived',
    thumbnail       VARCHAR(512)                    COMMENT '封面图 URL',
    tags            TEXT                            COMMENT '标签，JSON 数组字符串',
    metadata        TEXT                            COMMENT '扩展元数据，JSON',
    created_at      DATETIME NOT NULL               COMMENT '创建时间',
    updated_at      DATETIME NOT NULL               COMMENT '更新时间',
    deleted_at      DATETIME DEFAULT NULL           COMMENT '软删除时间，NULL 表示未删除'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='剧集项目表';


CREATE TABLE episodes (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '集 ID',
    drama_id        INT NOT NULL                    COMMENT '所属剧集 ID，关联 dramas.id',
    episode_number  INT NOT NULL                    COMMENT '集序号，从 1 开始',
    title           VARCHAR(255) NOT NULL           COMMENT '集标题',
    content         TEXT                            COMMENT '原始内容/大纲',
    script_content  TEXT                            COMMENT '格式化剧本正文，提取角色/场景用此字段',
    description     TEXT                            COMMENT '本集简介',
    duration        INT DEFAULT 0                   COMMENT '时长（秒）',
    status          VARCHAR(50) DEFAULT 'draft'     COMMENT '状态：draft/processing/done',
    video_url       VARCHAR(512)                    COMMENT '合成成片 URL',
    thumbnail       VARCHAR(512)                    COMMENT '封面图 URL',
    image_config_id INT DEFAULT NULL                COMMENT '关联图片生成配置 ID',
    video_config_id INT DEFAULT NULL                COMMENT '关联视频生成配置 ID',
    audio_config_id INT DEFAULT NULL                COMMENT '关联音频生成配置 ID',
    created_at      DATETIME NOT NULL               COMMENT '创建时间',
    updated_at      DATETIME NOT NULL               COMMENT '更新时间',
    deleted_at      DATETIME DEFAULT NULL           COMMENT '软删除时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分集表';


CREATE TABLE characters (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '角色 ID',
    drama_id        INT NOT NULL                    COMMENT '所属剧集 ID，关联 dramas.id',
    name            VARCHAR(255) NOT NULL           COMMENT '角色姓名，同剧集内唯一作为去重键',
    role            VARCHAR(100)                    COMMENT '角色定位：主角/配角/龙套',
    description     TEXT                            COMMENT '角色背景故事与人物关系',
    appearance      TEXT                            COMMENT '外貌描写：性别/年龄/体型/面部/发型/着装（300-500字）',
    personality     TEXT                            COMMENT '性格特点标签，如 冷静/腹黑/热血',
    voice_style     VARCHAR(255)                    COMMENT '声音风格描述',
    timbre_id       INT DEFAULT NULL                COMMENT '关联音色 ID，关联 timbres.id',
    image_url       VARCHAR(512)                    COMMENT '角色形象图 URL',
    reference_images TEXT                           COMMENT '参考图列表，JSON 数组',
    seed_value      VARCHAR(100)                    COMMENT '图片生成种子值，用于保持形象一致性',
    sort_order      INT DEFAULT NULL                COMMENT '排序权重，越小越靠前',
    local_path      VARCHAR(512)                    COMMENT '本地文件路径',
    voice_sample_url VARCHAR(512)                   COMMENT '声音样本 URL',
    voice_provider  VARCHAR(100)                    COMMENT '配音服务商，如 minimax',
    created_at      DATETIME NOT NULL               COMMENT '创建时间',
    updated_at      DATETIME NOT NULL               COMMENT '更新时间',
    deleted_at      DATETIME DEFAULT NULL           COMMENT '软删除时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色表';


-- 集与角色的多对多关联
-- 同一角色可出现在多集，同一集可有多个角色
CREATE TABLE episode_characters (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '关联 ID',
    episode_id      INT NOT NULL                    COMMENT '集 ID，关联 episodes.id',
    character_id    INT NOT NULL                    COMMENT '角色 ID，关联 characters.id',
    created_at      DATETIME NOT NULL               COMMENT '关联建立时间',
    UNIQUE KEY uq_ep_char (episode_id, character_id) COMMENT '防止重复关联'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='集-角色关联表';


CREATE TABLE scenes (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '场景 ID',
    drama_id        INT NOT NULL                    COMMENT '所属剧集 ID，关联 dramas.id',
    episode_id      INT DEFAULT NULL                COMMENT '首次出现的集 ID（可选），关联 episodes.id',
    location        TEXT NOT NULL                   COMMENT '地点名称，如 咖啡厅/皇宫大殿，与 time 组合作为去重键',
    time            TEXT NOT NULL                   COMMENT '时间段，如 清晨/深夜/黄昏，与 location 组合作为去重键',
    prompt          TEXT NOT NULL                   COMMENT '英文图片生成提示词，纯背景描述不含人物',
    storyboard_count INT DEFAULT 1                  COMMENT '关联分镜数量',
    image_url       VARCHAR(512)                    COMMENT '场景生成图 URL',
    status          VARCHAR(50) DEFAULT 'pending'   COMMENT '状态：pending/generating/done/failed',
    local_path      VARCHAR(512)                    COMMENT '本地文件路径',
    created_at      DATETIME NOT NULL               COMMENT '创建时间',
    updated_at      DATETIME NOT NULL               COMMENT '更新时间',
    deleted_at      DATETIME DEFAULT NULL           COMMENT '软删除时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景/背景表';


-- 集与场景的多对多关联
-- 同一场景可在多集复用，同一集可有多个场景
CREATE TABLE episode_scenes (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '关联 ID',
    episode_id      INT NOT NULL                    COMMENT '集 ID，关联 episodes.id',
    scene_id        INT NOT NULL                    COMMENT '场景 ID，关联 scenes.id',
    created_at      DATETIME NOT NULL               COMMENT '关联建立时间',
    UNIQUE KEY uq_ep_scene (episode_id, scene_id)   COMMENT '防止重复关联'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='集-场景关联表';


CREATE TABLE timbres (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '音色 ID',
    name            VARCHAR(100) NOT NULL           COMMENT '音色名称，如 龙小淳',
    gender          VARCHAR(20)                     COMMENT '性别：male/female',
    style           VARCHAR(255)                    COMMENT '风格描述，如 活泼甜美',
    provider        VARCHAR(100)                    COMMENT '服务商，如 aliyun/minimax',
    sample_url      VARCHAR(512)                    COMMENT '试听样本 URL',
    sort_order      INT DEFAULT 0                   COMMENT '排序权重',
    created_at      DATETIME NOT NULL               COMMENT '创建时间',
    updated_at      DATETIME NOT NULL               COMMENT '更新时间',
    deleted_at      DATETIME DEFAULT NULL           COMMENT '软删除'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='音色库表';