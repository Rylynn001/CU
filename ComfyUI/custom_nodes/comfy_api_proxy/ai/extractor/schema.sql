create table if not exists ai_voices
(
	id int auto_increment
		primary key,
	location text not null,
	voice_name text not null,
	description text null,
	language text null,
	created_at text not null,
	character_id int null
);

create table if not exists api_models
(
	id bigint auto_increment
		primary key,
	name varchar(255) not null,
	description text null,
	type varchar(32) default 'image' not null,
	provider varchar(255) null comment '提供商',
	rfid varchar(36) not null
)
engine=InnoDB collate=utf8mb4_unicode_ci;

create table if not exists api_providers
(
	id bigint auto_increment
		primary key,
	url varchar(512) not null,
	`key` text not null,
	created_at datetime default CURRENT_TIMESTAMP not null,
	updated_at datetime default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP
)
engine=InnoDB collate=utf8mb4_unicode_ci;

create table if not exists api_providers_backup
(
	id bigint auto_increment
		primary key,
	url varchar(512) not null,
	`key` text not null,
	created_at datetime default CURRENT_TIMESTAMP not null,
	updated_at datetime default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP
)
engine=InnoDB collate=utf8mb4_unicode_ci;

create table if not exists assets
(
	id bigint auto_increment,
	location varchar(500) null comment '存放地址',
	rfid bigint null comment 'user主键',
	asset_type varchar(20) default 'picture' null comment '资产类型：picture/video',
	tag int default 0 null,
	created_at datetime default CURRENT_TIMESTAMP null comment '创建时间',
	constraint assets_id_uindex
		unique (id)
);

create table if not exists characters
(
	id int auto_increment comment '角色 ID'
		primary key,
	drama_id int not null comment '所属剧集 ID，关联 dramas.id',
	name varchar(255) not null comment '角色姓名，同剧集内唯一作为去重键',
	role varchar(100) null comment '角色定位：主角/配角/龙套',
	description text null comment '角色背景故事与人物关系',
	appearance text null comment '外貌描写：性别/年龄/体型/面部/发型/着装（300-500字）',
	personality text null comment '性格特点标签，如 冷静/腹黑/热血',
	asset_id bigint null,
	reference_images text null comment '参考图列表，JSON 数组',
	seed_value varchar(100) null comment '图片生成种子值，用于保持形象一致性',
	sort_order int null comment '排序权重，越小越靠前',
	local_path varchar(512) null comment '本地文件路径',
	created_at datetime not null comment '创建时间',
	updated_at datetime not null comment '更新时间',
	deleted_at datetime null comment '软删除时间',
	voice_sample_id int null,
	timbre_id int null
)
comment '角色表' engine=InnoDB charset=utf8mb4;

create table if not exists dramas
(
	id int auto_increment comment '剧集 ID'
		primary key,
	title varchar(255) not null comment '剧集标题',
	description text null comment '剧集简介',
	genre varchar(100) null comment '剧集类型，如 爱情/古装/悬疑',
	style varchar(100) default 'realistic' null comment '视觉风格，如 realistic/anime',
	total_episodes int default 1 null comment '总集数',
	total_duration int default 0 null comment '总时长（秒）',
	status varchar(50) default 'draft' not null comment '状态：draft/published/archived',
	thumbnail varchar(512) null comment '封面图 URL',
	tags text null comment '标签，JSON 数组字符串',
	metadata text null comment '扩展元数据，JSON',
	created_at datetime not null comment '创建时间',
	updated_at datetime not null comment '更新时间',
	deleted_at datetime null comment '软删除时间，NULL 表示未删除'
)
comment '剧集项目表' engine=InnoDB charset=utf8mb4;

create table if not exists episode_characters
(
	id int auto_increment comment '关联 ID'
		primary key,
	episode_id int not null comment '集 ID，关联 episodes.id',
	character_id int not null comment '角色 ID，关联 characters.id',
	created_at datetime not null comment '关联建立时间',
	constraint uq_ep_char
		unique (episode_id, character_id) comment '防止重复关联'
)
comment '集-角色关联表' engine=InnoDB charset=utf8mb4;

create table if not exists episode_scenes
(
	id int auto_increment comment '关联 ID'
		primary key,
	episode_id int not null comment '集 ID，关联 episodes.id',
	scene_id int not null comment '场景 ID，关联 scenes.id',
	created_at datetime not null comment '关联建立时间',
	constraint uq_ep_scene
		unique (episode_id, scene_id) comment '防止重复关联'
)
comment '集-场景关联表' engine=InnoDB charset=utf8mb4;

create table if not exists episodes
(
	id int auto_increment comment '集 ID'
		primary key,
	drama_id int not null comment '所属剧集 ID，关联 dramas.id',
	episode_number int not null comment '集序号，从 1 开始',
	title varchar(255) not null comment '集标题',
	content text null comment '原始内容/大纲',
	script_content text null comment '格式化剧本正文，提取角色/场景用此字段',
	description text null comment '本集简介',
	duration int default 0 null comment '时长（秒）',
	status varchar(50) default 'draft' null comment '状态：draft/processing/done',
	video_url varchar(512) null comment '合成成片 URL',
	thumbnail varchar(512) null comment '封面图 URL',
	image_config_id int null comment '关联图片生成配置 ID',
	video_config_id int null comment '关联视频生成配置 ID',
	audio_config_id int null comment '关联音频生成配置 ID',
	created_at datetime not null comment '创建时间',
	updated_at datetime not null comment '更新时间',
	deleted_at datetime null comment '软删除时间'
)
comment '分集表' engine=InnoDB charset=utf8mb4;

create table if not exists history
(
	id bigint auto_increment
		primary key,
	task_id varchar(255) null comment '任务id',
	prompt text null comment '提示词',
	mode varchar(255) null comment '调用方法',
	status varchar(255) null comment '状态',
	type varchar(255) null comment '类型（文生图，图生图）',
	message text null comment '调用成功或失败的信息',
	input_file varchar(255) null comment '输入的图片或视频id集合',
	output_file varchar(255) null comment '输出的图片或视频id集合',
	user_id bigint null comment '关联user表中的主键',
	model_id bigint null comment '模型id',
	created_at datetime default CURRENT_TIMESTAMP null,
	payload text null,
	del_flag int default 0 null comment '删除标记，默认是0，删掉的是1'
)
comment '历史记录';

create table if not exists input_assets
(
	id int auto_increment
		primary key,
	rfid int not null,
	filename varchar(255) not null,
	location varchar(512) not null,
	created_at timestamp default CURRENT_TIMESTAMP null
)
engine=InnoDB charset=utf8mb4;

create table if not exists scenes
(
	id int auto_increment comment '场景 ID'
		primary key,
	drama_id int not null comment '所属剧集 ID，关联 dramas.id',
	episode_id int null comment '首次出现的集 ID（可选），关联 episodes.id',
	location text not null comment '地点名称，如 咖啡厅/皇宫大殿，与 time 组合作为去重键',
	time text not null comment '时间段，如 清晨/深夜/黄昏，与 location 组合作为去重键',
	prompt text not null comment '英文图片生成提示词，纯背景描述不含人物',
	storyboard_count int default 1 null comment '关联分镜数量',
	asset_id bigint null,
	status varchar(50) default 'pending' null comment '状态：pending/generating/done/failed',
	local_path varchar(512) null comment '本地文件路径',
	created_at datetime not null comment '创建时间',
	updated_at datetime not null comment '更新时间',
	deleted_at datetime null comment '软删除时间'
)
comment '场景/背景表' engine=InnoDB charset=utf8mb4;

create table if not exists storyboard_characters
(
	storyboard_id int not null,
	character_id int not null,
	primary key (storyboard_id, character_id)
);

create index idx_storyboard_characters_character_id
	on storyboard_characters (character_id);

create index idx_storyboard_characters_storyboard_id
	on storyboard_characters (storyboard_id);

create table if not exists storyboards
(
	id bigint auto_increment comment '主键ID'
		primary key,
	episode_id bigint not null comment '剧集ID',
	scene_id bigint null comment '场景ID',
	storyboard_number int not null comment '分镜编号',
	title varchar(255) null comment '标题',
	location varchar(255) null comment '地点',
	time varchar(100) null comment '时间',
	shot_type varchar(100) null comment '镜头类型',
	angle varchar(100) null comment '拍摄角度',
	movement varchar(100) null comment '运镜方式',
	action text null comment '动作描述',
	result text null comment '结果描述',
	atmosphere text null comment '氛围描述',
	image_prompt longtext null comment '图片提示词',
	video_prompt longtext null comment '视频提示词',
	bgm_prompt longtext null comment '背景音乐提示词',
	sound_effect text null comment '音效',
	dialogue text null comment '对白',
	description longtext null comment '描述',
	duration int default 0 not null comment '时长(秒)',
	composed_image varchar(500) null comment '合成图片',
	first_asset_id bigint null,
	last_asset_id bigint null,
	reference_images longtext null comment '参考图片(JSON)',
	video_url varchar(500) null comment '视频地址',
	subtitle_url varchar(500) null comment '字幕地址',
	composed_video_url varchar(500) null comment '最终合成视频地址',
	status varchar(20) default 'pending' not null comment '状态',
	created_at datetime default CURRENT_TIMESTAMP not null comment '创建时间',
	updated_at datetime default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '更新时间',
	deleted_at datetime null comment '删除时间',
	tts_audio_id int null
)
comment '分镜表' engine=InnoDB collate=utf8mb4_unicode_ci;

create index idx_created_at
	on storyboards (created_at);

create index idx_episode_id
	on storyboards (episode_id);

create index idx_scene_id
	on storyboards (scene_id);

create index idx_status
	on storyboards (status);

create index idx_storyboard_number
	on storyboards (storyboard_number);

create table if not exists sys_user
(
	id bigint auto_increment
		primary key,
	user_name varchar(255) null comment '用户名',
	password varchar(255) null comment '密码',
	constraint sys_username__uindex
		unique (user_name)
);

create table if not exists timbres
(
	id int auto_increment comment '音色 ID'
		primary key,
	name varchar(100) not null comment '音色名称，如 龙小淳',
	gender varchar(20) null comment '性别：male/female',
	provider varchar(100) null comment '服务商，如 aliyun/minimax',
	sample_url varchar(512) null comment '试听样本 URL',
	sort_order int default 0 null comment '排序权重',
	voice_id varchar(100) null,
	created_at datetime not null comment '创建时间',
	updated_at datetime not null comment '更新时间',
	deleted_at datetime null comment '软删除'
)
comment '音色库表' engine=InnoDB charset=utf8mb4;

