<template>
  <div class="studio" v-if="episode">
    <header class="topbar">
      <div class="topbar-left">
        <button class="back-btn" @click="router.push(`/drama/${dramaId}`)">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round">
            <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
          </svg>
          返回项目
        </button>
        <div class="studio-identity">
          <h1 class="studio-title">{{ episode.title }}</h1>
          <span class="episode-chip">第 {{ episodeNum }} 集</span>
          <span class="meta-inline">{{ chars.length }} 角色 · {{ sbs.length }} 镜头</span>
        </div>
      </div>
      <button class="btn-sm" @click="load">刷新</button>
    </header>

    <div class="studio-body">
      <aside class="sidebar">
        <nav class="pipeline">
          <div v-for="section in sidebarSections" :key="section.id" class="pipe-section">
            <div class="pipe-section-label">{{ section.label }}</div>
            <button
              v-for="item in section.items"
              :key="item.key"
              :class="['pipe-item', { active: activeKey === item.key, done: item.done }]"
              @click="activeKey = item.key"
            >
              <span class="pipe-icon">
                <svg v-if="item.done" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
                <span v-else class="pipe-dot" />
              </span>
              <span class="pipe-copy">
                <span class="pipe-label">{{ item.label }}</span>
                <span v-if="item.desc" class="pipe-sub">{{ item.desc }}</span>
              </span>
            </button>
          </div>
        </nav>
      </aside>

      <main class="main">
        <!-- 原始内容 -->
        <div v-if="activeKey === 'raw'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator">
              <span class="step-num">01</span>
              <span class="step-name">原始内容</span>
            </div>
            <div class="toolbar-right">
              <span v-if="localRaw" class="char-count">{{ localRaw.length }} 字</span>
              <button class="btn-sm btn-accent" @click="saveRaw">保存</button>
            </div>
          </div>
          <textarea class="fill-textarea" v-model="localRaw" placeholder="粘贴小说原文、故事大纲或分镜描述..." />
        </div>

        <!-- AI 改写 -->
        <div v-else-if="activeKey === 'rewrite'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator">
              <span class="step-num">02</span>
              <span class="step-name">AI 改写</span>
            </div>
            <div class="toolbar-right">
              <button class="btn-sm" @click="doRewrite" :disabled="running">
                {{ episode.script_content ? '重新改写' : '开始改写' }}
              </button>
              <button v-if="!episode.script_content" class="btn-sm" @click="skipRewrite">跳过改写</button>
            </div>
          </div>
          <div v-if="running && runningType === 'rewrite'" class="step-loading">
            <svg class="spin" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            <div class="loading-text">正在改写剧本...</div>
            <div class="loading-events">
              <div v-for="(ev, i) in agentEvents" :key="i" class="event-line">{{ ev }}</div>
            </div>
          </div>
          <div v-else-if="!episode.script_content" class="step-empty">
            <div class="empty-title">AI 改写为格式化剧本</div>
            <div class="empty-desc">可以先用 AI 把原始内容整理成格式化剧本，也可以跳过直接提取角色与场景</div>
            <div class="empty-actions">
              <button class="btn-primary" @click="doRewrite">开始改写</button>
              <button class="btn-ghost" @click="skipRewrite">跳过改写</button>
            </div>
          </div>
          <textarea v-else class="fill-textarea" v-model="localScript" />
        </div>

        <!-- 提取 -->
        <div v-else-if="activeKey === 'extract'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator">
              <span class="step-num">03</span>
              <span class="step-name">提取角色与场景</span>
            </div>
            <div class="toolbar-right">
              <span v-if="chars.length" class="char-count">{{ chars.length }} 角色 · {{ scenes.length }} 场景</span>
              <button class="btn-sm" @click="doExtract" :disabled="running">
                {{ chars.length ? '重新提取' : '开始提取' }}
              </button>
            </div>
          </div>
          <div v-if="running && runningType === 'extract'" class="step-loading">
            <svg class="spin" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            <div class="loading-text">正在提取角色和场景...</div>
            <div class="loading-events">
              <div v-for="(ev, i) in agentEvents" :key="i" class="event-line">{{ ev }}</div>
            </div>
          </div>
          <div v-else-if="!chars.length" class="step-empty">
            <div class="empty-title">从剧本提取角色与场景</div>
            <div class="empty-desc">AI 自动分析剧本，提取角色信息和场景列表，与项目已有数据智能去重合并</div>
            <button class="btn-primary" @click="doExtract">开始提取</button>
          </div>
          <div v-else class="extract-stage">
            <div class="card extract-summary">
              <div class="summary-kicker">Extraction Board</div>
              <div class="summary-title">角色与场景结果</div>
              <div class="summary-stats">
                <div class="summary-stat"><span>角色</span><strong>{{ chars.length }}</strong></div>
                <div class="summary-stat"><span>场景</span><strong>{{ scenes.length }}</strong></div>
              </div>
              <button class="summary-action" @click="activeKey = 'rewrite'">← AI 改写</button>
            </div>
            <div class="card extract-card">
              <div class="extract-head">角色 <span class="tag">{{ chars.length }}</span></div>
              <div class="extract-list">
                <div v-for="c in chars" :key="c.id" class="extract-row">
                  <div class="char-avatar">{{ c.name?.[0] || '?' }}</div>
                  <div class="extract-info">
                    <div class="extract-name-row">
                      <span class="extract-name">{{ c.name }}</span>
                      <span class="tag">{{ c.role || '角色' }}</span>
                    </div>
                    <div class="extract-meta">{{ c.description || c.appearance || '暂无描述' }}</div>
                  </div>
                </div>
              </div>
            </div>
            <div class="card extract-card" v-if="scenes.length">
              <div class="extract-head">场景 <span class="tag">{{ scenes.length }}</span></div>
              <div class="extract-list">
                <div v-for="s in scenes" :key="s.id" class="extract-row">
                  <div class="scene-dot" />
                  <div class="extract-info">
                    <div class="extract-name-row">
                      <span class="extract-name">{{ s.location }}</span>
                      <span v-if="s.time" class="tag">{{ s.time }}</span>
                    </div>
                    <div class="extract-meta">{{ s.prompt || '等待补充场景描述' }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 音色分配 -->
        <div v-else-if="activeKey === 'voice'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator">
              <span class="step-num">04</span>
              <span class="step-name">分配音色</span>
            </div>
            <div class="toolbar-right">
              <span v-if="charsVoiced > 0" class="char-count">{{ charsVoiced }}/{{ chars.length }} 已分配</span>
              <button v-if="charsVoiced > 0" class="btn-sm" @click="doVoiceAssign" :disabled="running">重新分配</button>
            </div>
          </div>
          <div v-if="running && runningType === 'voice'" class="step-loading">
            <svg class="spin" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            <div class="loading-text">正在分配音色...</div>
          </div>
          <div v-else-if="!chars.length" class="step-empty">
            <div class="empty-title">请先提取角色</div>
            <div class="empty-desc">需要先完成角色提取，才能分配音色</div>
            <button class="btn-primary" @click="activeKey = 'extract'">前往提取</button>
          </div>
          <div v-else-if="charsVoiced === 0" class="step-empty">
            <div class="empty-title">为角色分配合适的音色</div>
            <div class="empty-desc">AI 根据角色特征自动分配最匹配的 TTS 音色，也可手动选择</div>
            <button class="btn-primary" @click="doVoiceAssign">AI 自动分配</button>
          </div>
          <div v-else class="voice-stage">
            <div class="card voice-sidebar">
              <div class="voice-sidebar-kicker">Voice Casting</div>
              <div class="voice-sidebar-title">角色声音分配台</div>
              <div class="voice-sidebar-desc">先为每个角色选择合适音色，再生成试听。</div>
              <div class="voice-sidebar-stats">
                <div class="voice-stat"><span>已分配</span><strong>{{ charsVoiced }}/{{ chars.length }}</strong></div>
              </div>
              <div class="voice-lib-label">音色库 <span class="tag">{{ VOICE_PROFILES.length }}</span></div>
              <div class="voice-lib">
                <div v-for="v in VOICE_PROFILES" :key="v.id" class="voice-lib-item">
                  <div class="voice-lib-head">
                    <span class="voice-lib-name">{{ v.name }}</span>
                    <span class="tag">{{ v.gender }}</span>
                  </div>
                  <div class="voice-lib-traits">{{ v.style }}</div>
                </div>
              </div>
            </div>
            <div class="voice-grid">
              <div v-for="c in chars" :key="c.id" class="card voice-card">
                <div class="voice-card-head">
                  <div class="char-avatar">{{ c.name?.[0] || '?' }}</div>
                  <div class="voice-char-info">
                    <div class="voice-char-name-row">
                      <span class="extract-name">{{ c.name }}</span>
                      <span class="tag" :class="c.timbre_id ? 'tag-success' : ''">{{ c.timbre_id ? '已分配' : '待分配' }}</span>
                    </div>
                    <div class="extract-meta">{{ c.role || '角色' }}</div>
                  </div>
                </div>
                <div class="voice-card-desc">{{ c.description || c.appearance || '暂无角色描述' }}</div>
                <div class="voice-select-block">
                  <span class="field-label">选择音色</span>
                  <select class="input-select" :value="c.timbre_id || ''" @change="updateCharVoice(c.id, Number(($event.target as HTMLSelectElement).value))">
                    <option value="">请选择音色</option>
                    <option v-for="v in VOICE_PROFILES" :key="v.id" :value="v.id">{{ v.name }} · {{ v.gender }} · {{ v.style }}</option>
                  </select>
                </div>
                <div v-if="c.timbre_id && getVoiceProfile(c.timbre_id)" class="voice-profile-card">
                  <div class="voice-profile-head">
                    <span class="voice-profile-name">{{ getVoiceProfile(c.timbre_id)?.name }}</span>
                    <span class="tag">{{ getVoiceProfile(c.timbre_id)?.gender }}</span>
                  </div>
                  <div class="voice-profile-traits">{{ getVoiceProfile(c.timbre_id)?.style }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 分镜列表 -->
        <div v-else-if="activeKey === 'storyboard'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator">
              <span class="step-num">05</span>
              <span class="step-name">分镜列表</span>
            </div>
            <div class="toolbar-right">
              <span v-if="sbs.length" class="char-count">{{ sbs.length }} 镜头 · {{ totalDuration }}s</span>
              <button v-if="sbs.length" class="btn-sm" @click="addShot">+ 添加</button>
              <button class="btn-sm" @click="doBreakdown" :disabled="running">
                {{ running && runningType === 'storyboard' ? '拆解中...' : (sbs.length ? '重新拆解' : 'AI 拆解分镜') }}
              </button>
            </div>
          </div>
          <div v-if="running && runningType === 'storyboard'" class="step-loading">
            <svg class="spin" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            <div class="loading-text">正在拆解分镜并生成提示词...</div>
            <div class="loading-events">
              <div v-for="(ev, i) in agentEvents" :key="i" class="event-line">{{ ev }}</div>
            </div>
          </div>
          <div v-else-if="!sbs.length" class="step-empty">
            <div class="empty-title">将剧本拆解为分镜序列</div>
            <div class="empty-desc">AI 自动分析剧本，生成镜头列表和视频提示词</div>
            <button class="btn-primary" @click="doBreakdown">AI 拆解分镜</button>
          </div>
          <div v-else class="split-layout">
            <div class="shot-list">
              <div class="shot-list-head">
                <div>
                  <div class="shot-list-title">镜头序列</div>
                  <div class="shot-list-sub">按镜头顺序检查内容与素材状态</div>
                </div>
                <span class="tag mono">{{ totalDuration }}s</span>
              </div>
              <div class="shot-list-body">
                <div v-for="(sb, i) in sbs" :key="sb.id"
                  :class="['shot-item', { active: selectedSb?.id === sb.id }]"
                  @click="selectedSb = sb">
                  <div class="shot-item-header">
                    <div class="shot-num">#{{ String(i+1).padStart(2,'0') }}</div>
                    <span class="tag" style="font-size:10px">{{ sb.shot_type || '—' }}</span>
                    <div class="shot-status">
                      <div v-if="sb.dialogue" class="shot-dot has-dialogue" title="有对白"></div>
                      <div v-if="sb.image_prompt" class="shot-dot has-img" title="有图片提示词"></div>
                    </div>
                  </div>
                  <div class="shot-body">
                    <div class="shot-desc">{{ sb.description || sb.title || '无描述' }}</div>
                  </div>
                  <div class="shot-meta">
                    <span class="mono dim" style="font-size:10px">{{ sb.duration || 10 }}s</span>
                    <span v-if="sb.location" class="shot-location">{{ sb.location }}</span>
                    <span v-if="sb.dialogue" class="shot-dialogue">{{ sb.dialogue }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="detail-panel" v-if="selectedSb">
              <div class="detail-head">
                <div class="detail-head-copy">
                  <span class="detail-head-title">镜头 #{{ sbs.indexOf(selectedSb) + 1 }}</span>
                  <span class="detail-head-sub">{{ selectedSb.title || `镜头 ${sbs.indexOf(selectedSb)+1}` }} · {{ selectedSb.shot_type || '未设景别' }}</span>
                </div>
                <span class="tag mono">{{ selectedSb.duration || 10 }}s</span>
                <button class="btn-sm btn-danger ml-auto" @click="deleteShot(selectedSb)">删除</button>
              </div>
              <div class="detail-body">
                <div class="detail-section">
                  <div class="detail-section-head">
                    <span class="detail-section-title">镜头结构</span>
                    <span class="detail-section-copy">景别、角度、运镜、绑定关系和时长</span>
                  </div>
                  <div class="field-grid field-grid-4">
                    <label class="field">
                      <span class="field-label">标题</span>
                      <input :value="selectedSb.title || ''" class="input" @blur="updateField(selectedSb, 'title', ($event.target as HTMLInputElement).value)" placeholder="如：雪地逼近" />
                    </label>
                    <label class="field">
                      <span class="field-label">景别</span>
                      <input list="shot-type-list" :value="selectedSb.shot_type || ''" class="input" placeholder="选择或输入景别" @change="updateField(selectedSb, 'shot_type', ($event.target as HTMLInputElement).value)" />
                      <datalist id="shot-type-list"><option v-for="t in SHOT_TYPES" :key="t" :value="t" /></datalist>
                    </label>
                    <label class="field">
                      <span class="field-label">角度</span>
                      <input list="shot-angle-list" :value="selectedSb.angle || ''" class="input" placeholder="选择或输入角度" @change="updateField(selectedSb, 'angle', ($event.target as HTMLInputElement).value)" />
                      <datalist id="shot-angle-list"><option v-for="t in SHOT_ANGLES" :key="t" :value="t" /></datalist>
                    </label>
                    <label class="field">
                      <span class="field-label">运镜</span>
                      <input list="shot-move-list" :value="selectedSb.movement || ''" class="input" placeholder="选择或输入运镜" @change="updateField(selectedSb, 'movement', ($event.target as HTMLInputElement).value)" />
                      <datalist id="shot-move-list"><option v-for="t in SHOT_MOVEMENTS" :key="t" :value="t" /></datalist>
                    </label>
                  </div>
                  <div class="field-grid field-grid-4">
                    <label class="field">
                      <span class="field-label">绑定角色</span>
                      <div class="role-pills">
                        <button v-for="c in chars" :key="c.id" type="button"
                          :class="['role-pill', { active: isSbCharSelected(selectedSb, c.id) }]"
                          @click="toggleSbChar(selectedSb, c.id)">{{ c.name }}</button>
                        <span v-if="!chars.length" class="dim" style="font-size:12px">暂无角色</span>
                      </div>
                    </label>
                    <label class="field">
                      <span class="field-label">绑定场景</span>
                      <select class="input" :value="selectedSb.scene_id || ''" @change="updateField(selectedSb, 'scene_id', ($event.target as HTMLSelectElement).value ? Number(($event.target as HTMLSelectElement).value) : null)">
                        <option value="">未绑定场景</option>
                        <option v-for="s in scenes" :key="s.id" :value="s.id">{{ s.location }} · {{ s.time || '未设时间' }}</option>
                      </select>
                    </label>
                    <label class="field">
                      <span class="field-label">地点</span>
                      <input :value="selectedSb.location || ''" class="input" @blur="updateField(selectedSb, 'location', ($event.target as HTMLInputElement).value)" placeholder="场景地点" />
                    </label>
                    <label class="field">
                      <span class="field-label">时长(秒)</span>
                      <input :value="selectedSb.duration || 10" class="input" type="number" min="1" max="60" @blur="updateField(selectedSb, 'duration', Number(($event.target as HTMLInputElement).value))" />
                    </label>
                  </div>
                </div>
                <div class="detail-section">
                  <div class="detail-section-head">
                    <span class="detail-section-title">画面语义</span>
                    <span class="detail-section-copy">动作、结果、氛围和对白</span>
                  </div>
                  <div class="field-grid field-grid-2">
                    <label class="field">
                      <span class="field-label">动作</span>
                      <textarea :value="selectedSb.action || ''" class="textarea" rows="3" @blur="updateField(selectedSb, 'action', ($event.target as HTMLTextAreaElement).value)" placeholder="谁在做什么，表情和动作细节" />
                    </label>
                    <label class="field">
                      <span class="field-label">结果</span>
                      <textarea :value="selectedSb.result || ''" class="textarea" rows="3" @blur="updateField(selectedSb, 'result', ($event.target as HTMLTextAreaElement).value)" placeholder="镜头结束时的状态变化" />
                    </label>
                  </div>
                  <div class="field-grid field-grid-2">
                    <label class="field">
                      <span class="field-label">画面描述</span>
                      <textarea :value="selectedSb.description || ''" class="textarea" rows="4" @blur="updateField(selectedSb, 'description', ($event.target as HTMLTextAreaElement).value)" placeholder="描述画面内容..." />
                    </label>
                    <label class="field">
                      <span class="field-label">氛围</span>
                      <textarea :value="selectedSb.atmosphere || ''" class="textarea" rows="4" @blur="updateField(selectedSb, 'atmosphere', ($event.target as HTMLTextAreaElement).value)" placeholder="光线、色调、空气感、环境氛围" />
                    </label>
                  </div>
                  <label class="field">
                    <span class="field-label">对白 / 旁白</span>
                    <textarea :value="selectedSb.dialogue || ''" class="textarea" rows="3" @blur="updateField(selectedSb, 'dialogue', ($event.target as HTMLTextAreaElement).value)" placeholder="角色名：台词内容 或 旁白：内容" />
                  </label>
                </div>
                <div class="detail-section">
                  <div class="detail-section-head">
                    <span class="detail-section-title">生成提示</span>
                    <span class="detail-section-copy">图片、视频、配乐和音效</span>
                  </div>
                  <label class="field">
                    <span class="field-label">静态画面提示词</span>
                    <textarea :value="selectedSb.image_prompt || ''" class="textarea" rows="4" @blur="updateField(selectedSb, 'image_prompt', ($event.target as HTMLTextAreaElement).value)" placeholder="用于首帧、尾帧和镜头图片的单帧画面提示词" />
                  </label>
                  <label class="field">
                    <span class="field-label">视频提示词</span>
                    <textarea :value="selectedSb.video_prompt || ''" class="textarea" rows="5" @blur="updateField(selectedSb, 'video_prompt', ($event.target as HTMLTextAreaElement).value)" placeholder="按 3 秒分段的视频提示词..." />
                  </label>
                  <div class="field-grid field-grid-2">
                    <label class="field">
                      <span class="field-label">配乐提示词</span>
                      <textarea :value="selectedSb.bgm_prompt || ''" class="textarea" rows="3" @blur="updateField(selectedSb, 'bgm_prompt', ($event.target as HTMLTextAreaElement).value)" placeholder="如：压抑低频弦乐，缓慢推进" />
                    </label>
                    <label class="field">
                      <span class="field-label">音效提示词</span>
                      <textarea :value="selectedSb.sound_effect || ''" class="textarea" rows="3" @blur="updateField(selectedSb, 'sound_effect', ($event.target as HTMLTextAreaElement).value)" placeholder="如：风雪声、脚踩积雪、衣料摩擦声" />
                    </label>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="detail-panel detail-empty">
              <div class="dim">← 点击左侧镜头查看详情</div>
            </div>
          </div>
        </div>
        <!-- 角色形象 -->
        <div v-else-if="activeKey === 'prod-chars'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator"><span class="step-num">06</span><span class="step-name">角色形象</span></div>
            <div class="toolbar-right">
              <span class="char-count">{{ chars.length }} 角色 · {{ charsWithImage }}/{{ chars.length }} 已生成</span>
            </div>
          </div>
          <div v-if="!chars.length" class="step-empty">
            <div class="empty-title">暂无角色</div>
            <div class="empty-desc">请先在剧本流程中提取角色</div>
            <button class="btn-primary" @click="activeKey = 'extract'">前往提取</button>
          </div>
          <div v-else class="prod-scroll">
            <div class="asset-grid">
              <div v-for="c in chars" :key="c.id" class="card asset-card">
                <div class="asset-cover">
                  <img v-if="c.image_url" :src="locationToUrl(c.image_url) ?? undefined" class="asset-img" />
                  <div v-else class="asset-placeholder">
                    <span class="asset-initial">{{ c.name?.[0] || '?' }}</span>
                  </div>
                  <span class="asset-badge" :class="c.image_url ? 'badge-ok' : ''">{{ c.image_url ? '已生成' : '待生成' }}</span>
                </div>
                <div class="asset-body">
                  <div class="asset-name">{{ c.name }}</div>
                  <div class="asset-meta dim">{{ c.role || '角色' }}</div>
                  <div v-if="c.appearance" class="asset-desc dim">{{ c.appearance?.slice(0,60) }}{{ (c.appearance?.length||0)>60?'...':'' }}</div>
                </div>
                <div class="asset-foot">
                  <span :class="['dot', c.image_url ? 'ok' : '', pendingCharIds.has(c.id) ? 'pending' : '']" />
                  <span class="dim" style="font-size:10px">{{ pendingCharIds.has(c.id) ? '生成中...' : (c.image_url ? '已生成' : '待生成') }}</span>
                  <button class="btn-sm ml-auto" :disabled="pendingCharIds.has(c.id)" @click="genCharImage(c)">
                    {{ pendingCharIds.has(c.id) ? '生成中' : (c.image_url ? '重新生成' : '生成') }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
        <!-- 场景图片 -->
        <div v-else-if="activeKey === 'prod-scenes'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator"><span class="step-num">07</span><span class="step-name">场景图片</span></div>
            <div class="toolbar-right">
              <span class="char-count">{{ scenes.length }} 场景 · {{ scenesWithImage }}/{{ scenes.length }} 已生成</span>
            </div>
          </div>
          <div v-if="!scenes.length" class="step-empty">
            <div class="empty-title">暂无场景</div>
            <div class="empty-desc">请先在剧本流程中提取场景</div>
            <button class="btn-primary" @click="activeKey = 'extract'">前往提取</button>
          </div>
          <div v-else class="prod-scroll">
            <div class="asset-grid">
              <div v-for="s in scenes" :key="s.id" class="card asset-card">
                <div class="asset-cover wide">
                  <img v-if="s.image_url" :src="locationToUrl(s.image_url) ?? undefined" class="asset-img" />
                  <div v-else class="asset-placeholder">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                  </div>
                  <span class="asset-badge" :class="s.image_url ? 'badge-ok' : ''">{{ s.image_url ? '已生成' : '待生成' }}</span>
                </div>
                <div class="asset-body">
                  <div class="asset-name">{{ s.location }}</div>
                  <div class="asset-meta dim">{{ s.time || '—' }}</div>
                  <div v-if="s.prompt" class="asset-desc dim">{{ s.prompt?.slice(0,60) }}{{ (s.prompt?.length||0)>60?'...':'' }}</div>
                </div>
                <div class="asset-foot">
                  <span :class="['dot', s.image_url ? 'ok' : '', pendingSceneIds.has(s.id) ? 'pending' : '']" />
                  <span class="dim" style="font-size:10px">{{ pendingSceneIds.has(s.id) ? '生成中...' : (s.image_url ? '已生成' : '待生成') }}</span>
                  <button class="btn-sm ml-auto" :disabled="pendingSceneIds.has(s.id)" @click="genSceneImage(s)">
                    {{ pendingSceneIds.has(s.id) ? '生成中' : (s.image_url ? '重新生成' : '生成') }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 配音生成 -->
        <div v-else-if="activeKey === 'prod-dubbing'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator"><span class="step-num">08</span><span class="step-name">配音生成</span></div>
            <div class="toolbar-right">
              <span class="char-count">{{ ttsEligibleCount }} 条有对白 · {{ ttsGeneratedCount }} 已生成</span>
            </div>
          </div>
          <div v-if="!sbs.length" class="step-empty">
            <div class="empty-title">暂无分镜</div>
            <div class="empty-desc">请先完成分镜拆解</div>
            <button class="btn-primary" @click="activeKey = 'storyboard'">前往分镜</button>
          </div>
          <div v-else-if="!ttsEligibleCount" class="step-empty">
            <div class="empty-title">暂无可配音镜头</div>
            <div class="empty-desc">在分镜列表中为镜头填写对白，格式如：角色名：台词</div>
            <button class="btn-primary" @click="activeKey = 'storyboard'">前往分镜</button>
          </div>
          <div v-else class="prod-scroll">
            <div class="dub-grid">
              <div v-for="(sb, i) in sbsWithDialogue" :key="sb.id" class="card dub-card">
                <div class="dub-head">
                  <div class="dub-copy">
                    <div class="dub-title">
                      <span class="frame-num">#{{ String(sb.storyboard_number || i+1).padStart(2,'0') }}</span>
                      <span class="frame-badge">{{ getDialogueSpeaker(sb) }}</span>
                    </div>
                    <div class="dub-desc">{{ getDialogueText(sb) }}</div>
                  </div>
                  <span class="tag" :class="sb.tts_audio_url ? 'tag-success' : ''">{{ sb.tts_audio_url ? '已生成' : '待生成' }}</span>
                </div>
                <div class="dub-meta">
                  <span class="dim">{{ sb.shot_type || '未设景别' }}</span>
                  <span class="dim">{{ sb.duration || 10 }}s</span>
                </div>
                <div class="dub-foot">
                  <audio v-if="sb.tts_audio_url" :src="sb.tts_audio_url" controls preload="none" class="dub-audio" />
                  <div v-else class="dim" style="font-size:12px">尚未生成语音</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 镜头图片 -->
        <div v-else-if="activeKey === 'prod-shots'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator"><span class="step-num">09</span><span class="step-name">镜头图片</span></div>
            <div class="toolbar-right">
              <span class="char-count">{{ sbs.length }} 镜头 · {{ sbsWithImage }}/{{ sbs.length }} 已有首帧</span>
              <div class="frame-mode-toggle">
                <button :class="['btn-sm', frameMode === 'first' ? 'active' : '']" @click="frameMode = 'first'">仅首帧</button>
                <button :class="['btn-sm', frameMode === 'first_last' ? 'active' : '']" @click="frameMode = 'first_last'">首尾帧</button>
              </div>
            </div>
          </div>
          <div v-if="!sbs.length" class="step-empty">
            <div class="empty-title">暂无分镜</div>
            <button class="btn-primary" @click="activeKey = 'storyboard'">前往分镜</button>
          </div>
          <div v-else class="shot-frame-scroll">
            <div class="shot-frame-grid">
              <div v-for="(sb, i) in sbs" :key="sb.id" class="card shot-frame-row">
                <div class="shot-frame-info">
                  <div class="shot-frame-top">
                    <span class="frame-num">#{{ String(sb.storyboard_number || i+1).padStart(2,'0') }}</span>
                    <span class="frame-badge">{{ sb.shot_type || '—' }}</span>
                  </div>
                  <div class="shot-frame-desc">{{ sb.description || sb.title || '—' }}</div>
                  <div class="shot-frame-meta">
                    <span :class="['dot', getFirstFrame(sb) ? 'ok' : '', isPendingShotFrame(sb.id, 'first_frame') ? 'pending' : '']" />
                    <span class="dim" style="font-size:11px">首帧</span>
                    <template v-if="frameMode === 'first_last'">
                      <span :class="['dot', getLastFrame(sb) ? 'ok' : '', isPendingShotFrame(sb.id, 'last_frame') ? 'pending' : '']" />
                      <span class="dim" style="font-size:11px">尾帧</span>
                    </template>
                    <span class="dim" style="font-size:11px">· {{ sb.duration || 10 }}s</span>
                  </div>
                </div>
                <div class="shot-frame-thumbs">
                  <!-- 首帧 -->
                  <div class="shot-frame-thumb-wrap">
                    <div class="shot-frame-thumb" @click="!isPendingShotFrame(sb.id, 'first_frame') && genShotFrame(sb, 'first_frame')">
                      <img v-if="getFirstFrame(sb)" :src="getFirstFrame(sb)!" class="shot-frame-img" />
                      <div v-else class="shot-frame-empty">
                        <svg v-if="isPendingShotFrame(sb.id, 'first_frame')" class="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                      </div>
                      <span v-if="getFirstFrame(sb) && !isPendingShotFrame(sb.id, 'first_frame')" class="shot-frame-re">
                        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                      </span>
                    </div>
                    <span class="shot-frame-label">{{ isPendingShotFrame(sb.id, 'first_frame') ? '生成中' : '首帧' }}</span>
                  </div>
                  <!-- 尾帧（仅首尾帧模式） -->
                  <div v-if="frameMode === 'first_last'" class="shot-frame-thumb-wrap">
                    <div class="shot-frame-thumb" @click="!isPendingShotFrame(sb.id, 'last_frame') && genShotFrame(sb, 'last_frame')">
                      <img v-if="getLastFrame(sb)" :src="getLastFrame(sb)!" class="shot-frame-img" />
                      <div v-else class="shot-frame-empty">
                        <svg v-if="isPendingShotFrame(sb.id, 'last_frame')" class="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                      </div>
                      <span v-if="getLastFrame(sb) && !isPendingShotFrame(sb.id, 'last_frame')" class="shot-frame-re">
                        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                      </span>
                    </div>
                    <span class="shot-frame-label">{{ isPendingShotFrame(sb.id, 'last_frame') ? '生成中' : '尾帧' }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 视频生成 -->
        <div v-else-if="activeKey === 'prod-videos'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator"><span class="step-num">10</span><span class="step-name">视频生成</span></div>
            <div class="toolbar-right">
              <span class="char-count">{{ sbs.length }} 镜头 · {{ sbsWithVideo }}/{{ sbs.length }} 已生成</span>
            </div>
          </div>
          <div v-if="!sbs.length" class="step-empty">
            <div class="empty-title">暂无分镜</div>
            <button class="btn-primary" @click="activeKey = 'storyboard'">前往分镜</button>
          </div>
          <div v-else class="prod-scroll">
            <div class="prod-grid">
              <div v-for="(sb, i) in sbs" :key="sb.id" class="card prod-card">
                <div class="prod-cover">
                  <video v-if="sb.video_url" :src="sb.video_url" class="prod-video" controls preload="metadata" playsinline />
                  <img v-else-if="sb.image_url" :src="locationToUrl(sb.image_url) ?? undefined" class="asset-img" />
                <div v-else class="prod-cover-empty">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
                  </div>
                  <span class="prod-idx">#{{ String(i+1).padStart(2,'0') }}</span>
                </div>
                <div class="prod-info">
                  <div class="prod-desc truncate">{{ sb.description || sb.title || '—' }}</div>
                  <div class="prod-meta-line">{{ sb.shot_type || '未设景别' }} · {{ sb.duration || 10 }}s</div>
                  <div class="prod-dots">
                    <span :class="['dot', sb.image_url ? 'ok' : '']" /><span style="font-size:10px">图</span>
                    <span :class="['dot', sb.video_url ? 'ok' : '']" /><span style="font-size:10px">视频</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 视频合成 -->
        <div v-else-if="activeKey === 'prod-compose'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator"><span class="step-num">11</span><span class="step-name">视频合成</span></div>
            <div class="toolbar-right">
              <span class="char-count">{{ sbs.length }} 镜头 · {{ sbsComposed }}/{{ sbs.length }} 已合成</span>
            </div>
          </div>
          <div v-if="!sbs.length" class="step-empty">
            <div class="empty-title">暂无分镜</div>
            <button class="btn-primary" @click="activeKey = 'storyboard'">前往分镜</button>
          </div>
          <div v-else class="prod-scroll">
            <div class="prod-grid">
              <div v-for="(sb, i) in sbs" :key="sb.id" class="card prod-card">
                <div class="prod-cover">
                  <video v-if="sb.composed_video_url" :src="sb.composed_video_url" class="prod-video" controls preload="metadata" playsinline />
                  <video v-else-if="sb.video_url" :src="sb.video_url" class="prod-video" controls preload="metadata" playsinline />
                  <img v-else-if="sb.image_url" :src="locationToUrl(sb.image_url) ?? undefined" class="asset-img" />
                  <div v-else class="prod-cover-empty">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                  </div>
                  <span class="prod-idx">#{{ String(i+1).padStart(2,'0') }}</span>
                  <span v-if="sb.composed_video_url" class="prod-overlay-badge">已合成</span>
                </div>
                <div class="prod-info">
                  <div class="prod-desc truncate">{{ sb.description || sb.title || '—' }}</div>
                  <div class="prod-meta-line">{{ sb.shot_type || '未设景别' }} · {{ sb.duration || 10 }}s</div>
                  <div class="prod-dots">
                    <span :class="['dot', sb.video_url ? 'ok' : '']" /><span style="font-size:10px">视频</span>
                    <span :class="['dot', sb.tts_audio_url ? 'ok' : '']" /><span style="font-size:10px">配音</span>
                    <span :class="['dot', sb.composed_video_url ? 'ok' : '']" /><span style="font-size:10px">合成</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 拼接导出 -->
        <div v-else-if="activeKey === 'prod-export'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator"><span class="step-num">12</span><span class="step-name">拼接导出</span></div>
            <div class="toolbar-right">
              <span class="char-count">{{ sbsComposed }}/{{ sbs.length }} 镜头已合成</span>
            </div>
          </div>
          <div class="export-body">
            <div class="card export-card">
              <div class="export-kicker">Final Export</div>
              <div class="export-title">全集拼接</div>
              <div class="export-desc">将所有已合成镜头按顺序拼接为完整视频</div>
              <div class="export-stats">
                <div class="export-stat"><span>总镜头</span><strong>{{ sbs.length }}</strong></div>
                <div class="export-stat"><span>已合成</span><strong>{{ sbsComposed }}</strong></div>
                <div class="export-stat"><span>总时长</span><strong>{{ totalDuration }}s</strong></div>
              </div>
              <div v-if="episode?.merged_video_url" class="export-video-wrap">
                <video :src="episode.merged_video_url" controls class="export-video" />
              </div>
              <div v-else class="export-empty">
                <div class="dim" style="font-size:13px">尚未导出</div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>

  <div v-else-if="loading" class="loading-full">
    <svg class="spin" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { pollTaskUntilDone } from '../api/apiService'
import { getCurrentUserId } from '../utils/user'

const router = useRouter()
const route = useRoute()
const BASE = '/api/api-proxy'

const dramaId = Number(route.params.id)
const episodeNum = Number(route.params.num)

const episode = ref<any>(null)
const loading = ref(false)
const chars = ref<any[]>([])
const scenes = ref<any[]>([])
const sbs = ref<any[]>([])
const localRaw = ref('')
const localScript = ref('')
const running = ref(false)
const runningType = ref<string | null>(null)
const agentEvents = ref<string[]>([])
const activeKey = ref('raw')
const selectedSb = ref<any>(null)
const frameMode = ref<'first' | 'first_last'>('first')
const pendingShotFrameKeys = ref<string[]>([])

const VOICE_PROFILES = ref<{id: number, name: string, gender: string, style: string}[]>([])

async function loadVoices() {
  const res = await fetch(`${BASE}/timbres`)
  const data = await res.json()
  VOICE_PROFILES.value = data.items || []
}

function getVoiceProfile(id: number) {
  return VOICE_PROFILES.value.find(v => v.id === id)
}

const SHOT_TYPES = ['全景', '远景', '中景', '近景', '特写', '大特写', '过肩镜头', '两人镜头']
const SHOT_ANGLES = ['平视', '仰视', '俯视', '斜角', '正面', '侧面', '背面']
const SHOT_MOVEMENTS = ['固定', '推镜', '拉镜', '摇镜', '移镜', '跟镜', '环绕', '手持']

const charsVoiced = computed(() => chars.value.filter(c => c.timbre_id).length)
const totalDuration = computed(() => sbs.value.reduce((s, b) => s + (b.duration || 10), 0))

const charsWithImage = computed(() => chars.value.filter(c => c.image_url).length)
const scenesWithImage = computed(() => scenes.value.filter(s => s.image_url).length)
const sbsWithImage = computed(() => sbs.value.filter(s => s.image_url).length)
const sbsWithVideo = computed(() => sbs.value.filter(s => s.video_url).length)
const sbsComposed = computed(() => sbs.value.filter(s => s.composed_video_url).length)
const sbsWithDialogue = computed(() => sbs.value.filter(s => s.dialogue))
const ttsEligibleCount = computed(() => sbsWithDialogue.value.length)
const ttsGeneratedCount = computed(() => sbs.value.filter(s => s.dialogue && s.tts_audio_url).length)

// 角色/场景/镜头图片生成
const pendingCharIds = ref<Set<number>>(new Set())
const pendingSceneIds = ref<Set<number>>(new Set())
const pendingShotIds = ref<Set<number>>(new Set())
const IMAGE_MODEL_ID = 4

async function genImage(
  id: number,
  prompt: string,
  pendingSet: typeof pendingCharIds,
  saveAsset: (assetId: number, url: string) => Promise<void>,
  label: string,
) {
  if (pendingSet.value.has(id)) return
  if (!prompt) { ElMessage.warning(`${label} 缺少描述，无法生成`); return }
  pendingSet.value = new Set([...pendingSet.value, id])
  try {
    const userId = getCurrentUserId()
    const res = await fetch(`${BASE}/txt2img`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: IMAGE_MODEL_ID, prompt, aspect_ratio: '1:1', user_id: userId }),
    })
    if (!res.ok) throw new Error(await res.text())
    const { task_id } = await res.json()
    const result = await pollTaskUntilDone(task_id, userId ?? undefined, 'image')
    const img = result.images?.[0]
    if (!img?.url) throw new Error('生成结果中没有图片 URL')
    if (!img.asset_id) throw new Error('生成结果中没有 asset_id')
    await saveAsset(img.asset_id, img.url)
    ElMessage.success(`${label} 已生成`)
  } catch (e: any) {
    ElMessage.error(e.message || '生成失败')
  } finally {
    const next = new Set(pendingSet.value)
    next.delete(id)
    pendingSet.value = next
  }
}

function genCharImage(c: any) {
  return genImage(
    c.id,
    c.appearance || c.personality || c.name,
    pendingCharIds,
    async (assetId, url) => {
      await fetch(`${BASE}/characters/${c.id}/image`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asset_id: assetId }),
      })
      c.asset_id = assetId
      c.image_url = url
    },
    c.name,
  )
}

function genSceneImage(s: any) {
  return genImage(
    s.id,
    s.prompt || s.location,
    pendingSceneIds,
    async (assetId, url) => {
      await fetch(`${BASE}/scenes/${s.id}/image`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asset_id: assetId }),
      })
      s.asset_id = assetId
      s.image_url = url
    },
    s.location,
  )
}

function genShotImage(sb: any) {
  return genImage(
    sb.id,
    sb.image_prompt || sb.description || sb.title,
    pendingShotIds,
    async (url) => {
      await fetch(`${BASE}/storyboards/${sb.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_url: url }),
      })
      sb.image_url = url
    },
    `镜头 #${sb.storyboard_number || sb.id}`,
  )
}

function locationToUrl(location: string | null | undefined): string | null {
  if (!location) return null
  const filename = location.replace(/\\/g, '/').split('/').pop()!
  return `/api/view?filename=${encodeURIComponent(filename)}&type=output`
}

function getFirstFrame(sb: any): string | null {
  return locationToUrl(sb?.first_frame_image || sb?.firstFrameImage)
}

function getLastFrame(sb: any): string | null {
  return locationToUrl(sb?.last_frame_image || sb?.lastFrameImage)
}

function framePendingKey(id: number, frameType: string) {
  return `${id}:${frameType}`
}

function isPendingShotFrame(id: number, frameType: string) {
  return pendingShotFrameKeys.value.includes(framePendingKey(id, frameType))
}

// 收集镜头绑定的角色和场景的 asset_id（直接用于图生图）
function getShotRefAssetIds(sb: any): number[] {
  const ids: number[] = []
  const scene = scenes.value.find((s: any) => s.id === sb.scene_id || s.id === sb.sceneId)
  if (scene?.asset_id) ids.push(scene.asset_id)
  const charIdList: number[] = sb.character_ids
    ? String(sb.character_ids).split(',').map(Number).filter(Boolean)
    : []
  for (const cid of charIdList) {
    const c = chars.value.find((x: any) => x.id === cid)
    if (c?.asset_id) ids.push(c.asset_id)
  }
  return ids
}

function buildFramePrompt(sb: any, frameType: 'first_frame' | 'last_frame'): string {
  const base = sb.image_prompt || sb.description || sb.title || ''
  const hint = frameType === 'first_frame'
    ? '生成这个镜头的起始关键帧，突出建立关系和动作开始瞬间'
    : '生成这个镜头的结束关键帧，突出动作结束、情绪落点或结果状态'
  return base ? `${base}；${hint}` : hint
}

async function genShotFrame(sb: any, frameType: 'first_frame' | 'last_frame') {
  const basePrompt = sb.image_prompt || sb.description || sb.title
  if (!basePrompt) { ElMessage.warning('镜头缺少描述，无法生成'); return }
  const key = framePendingKey(sb.id, frameType)
  if (pendingShotFrameKeys.value.includes(key)) return
  pendingShotFrameKeys.value = [...pendingShotFrameKeys.value, key]
  try {
    const userId = getCurrentUserId()
    const prompt = buildFramePrompt(sb, frameType)
    const input_asset_ids = getShotRefAssetIds(sb)

    const body: any = { model: IMAGE_MODEL_ID, prompt, aspect_ratio: '16:9', user_id: userId }
    if (input_asset_ids.length) body.input_asset_ids = input_asset_ids

    const res = await fetch(`${BASE}/txt2img`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(await res.text())
    const { task_id } = await res.json()
    const result = await pollTaskUntilDone(task_id, userId ?? undefined, 'image')
    const img = result.images?.[0]
    if (!img?.url) throw new Error('生成结果中没有图片 URL')
    if (!img.asset_id) throw new Error('生成结果中没有 asset_id')
    const assetField = frameType === 'first_frame' ? 'first_asset_id' : 'last_asset_id'
    const imgField = frameType === 'first_frame' ? 'first_frame_image' : 'last_frame_image'
    await fetch(`${BASE}/storyboards/${sb.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [assetField]: img.asset_id }),
    })
    sb[assetField] = img.asset_id
    sb[imgField] = img.url
    ElMessage.success(frameType === 'first_frame' ? '首帧已生成' : '尾帧已生成')
  } catch (e: any) {
    ElMessage.error(e.message || '生成失败')
  } finally {
    pendingShotFrameKeys.value = pendingShotFrameKeys.value.filter(k => k !== key)
  }
}

function getDialogueSpeaker(sb: any): string {
  const d = sb.dialogue || ''
  const m = d.match(/^([^：:]+)[：:]/)
  return m ? m[1].trim() : '旁白'
}

function getDialogueText(sb: any): string {
  const d = sb.dialogue || ''
  const m = d.match(/^[^：:]+[：:](.*)/)
  return m ? m[1].trim() : d
}

const sidebarSections = computed(() => [
  {
    id: 'script',
    label: '剧本',
    items: [
      { key: 'raw',        label: '原始内容',    desc: localRaw.value ? `${localRaw.value.length} 字` : '', done: !!localRaw.value },
      { key: 'rewrite',    label: 'AI 改写',     desc: '', done: !!episode.value?.script_content },
      { key: 'extract',    label: '提取角色与场景', desc: chars.value.length ? `${chars.value.length} 角色` : '', done: chars.value.length > 0 },
      { key: 'voice',      label: '分配音色',    desc: charsVoiced.value ? `${charsVoiced.value}/${chars.value.length} 已分配` : '', done: charsVoiced.value > 0 && charsVoiced.value === chars.value.length },
      { key: 'storyboard', label: '分镜列表',    desc: sbs.value.length ? `${sbs.value.length} 镜头` : '', done: sbs.value.length > 0 },
    ],
  },
  {
    id: 'prod',
    label: '制作',
    items: [
      { key: 'prod-chars',   label: '角色形象',   desc: chars.value.length ? `${charsWithImage.value}/${chars.value.length}` : '', done: charsWithImage.value > 0 && charsWithImage.value === chars.value.length },
      { key: 'prod-scenes',  label: '场景图片',   desc: scenes.value.length ? `${scenesWithImage.value}/${scenes.value.length}` : '', done: scenesWithImage.value > 0 && scenesWithImage.value === scenes.value.length },
      { key: 'prod-dubbing', label: '配音生成',   desc: ttsEligibleCount.value ? `${ttsGeneratedCount.value}/${ttsEligibleCount.value}` : '', done: ttsGeneratedCount.value > 0 && ttsGeneratedCount.value === ttsEligibleCount.value },
      { key: 'prod-shots',   label: '镜头图片',   desc: sbs.value.length ? `${sbsWithImage.value}/${sbs.value.length}` : '', done: sbsWithImage.value > 0 && sbsWithImage.value === sbs.value.length },
      { key: 'prod-videos',  label: '视频生成',   desc: sbs.value.length ? `${sbsWithVideo.value}/${sbs.value.length}` : '', done: sbsWithVideo.value > 0 && sbsWithVideo.value === sbs.value.length },
      { key: 'prod-compose', label: '视频合成',   desc: sbs.value.length ? `${sbsComposed.value}/${sbs.value.length}` : '', done: sbsComposed.value > 0 && sbsComposed.value === sbs.value.length },
      { key: 'prod-export',  label: '拼接导出',   desc: episode.value?.merged_video_url ? '已导出' : '', done: !!episode.value?.merged_video_url },
    ],
  },
])

function isSbCharSelected(sb: any, charId: number) {
  if (!sb.character_ids) return false
  return String(sb.character_ids).split(',').map(Number).includes(charId)
}

async function toggleSbChar(sb: any, charId: number) {
  const ids = sb.character_ids ? String(sb.character_ids).split(',').map(Number).filter(Boolean) : []
  const idx = ids.indexOf(charId)
  if (idx >= 0) ids.splice(idx, 1)
  else ids.push(charId)
  await updateField(sb, 'character_ids', ids.join(','))
}

async function load() {
  loading.value = true
  try {
    const res = await fetch(`${BASE}/dramas/${dramaId}/episodes/${episodeNum}`)
    if (!res.ok) throw new Error('加载失败')
    episode.value = await res.json()
    localRaw.value = episode.value.content || ''
    localScript.value = episode.value.script_content || ''

    const [cRes, sRes, sbRes] = await Promise.all([
      fetch(`${BASE}/episodes/${episode.value.id}/characters`),
      fetch(`${BASE}/episodes/${episode.value.id}/scenes`),
      fetch(`${BASE}/episodes/${episode.value.id}/storyboards`),
    ])
    chars.value = (await cRes.json()).items || []
    scenes.value = (await sRes.json()).items || []
    sbs.value = (await sbRes.json()).items || []
    await loadVoices()

    if (sbs.value.length) activeKey.value = 'storyboard'
    else if (chars.value.length) activeKey.value = 'extract'
    else if (episode.value.script_content) activeKey.value = 'rewrite'
    else activeKey.value = 'raw'
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function saveRaw() {
  if (!episode.value) return
  await fetch(`${BASE}/episodes/${episode.value.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: localRaw.value }),
  })
  episode.value.content = localRaw.value
  ElMessage.success('已保存')
}

async function skipRewrite() {
  if (!episode.value) return
  await fetch(`${BASE}/episodes/${episode.value.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script_content: localRaw.value }),
  })
  episode.value.script_content = localRaw.value
  localScript.value = localRaw.value
  activeKey.value = 'extract'
  ElMessage.success('已跳过改写，内容已同步')
}

async function streamAgent(url: string, body: Record<string, any>, type: string) {
  running.value = true
  runningType.value = type
  agentEvents.value = []
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok || !res.body) throw new Error('请求失败')
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let lastEvent = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('event: ')) { lastEvent = line.slice(7).trim(); continue }
        if (line.startsWith('data: ')) {
          try {
            const d = JSON.parse(line.slice(6))
            if (d.tool) agentEvents.value.push(`调用工具：${d.tool}`)
            if (d.text) agentEvents.value.push(d.text.slice(0, 60))
            if (agentEvents.value.length > 20) agentEvents.value.shift()
          } catch { /**/ }
        }
      }
    }
    return lastEvent
  } finally {
    running.value = false
    runningType.value = null
  }
}

async function doRewrite() {
  if (!episode.value) return
  running.value = true
  runningType.value = 'rewrite'
  agentEvents.value = []
  try {
    const res = await fetch(`${BASE}/agent/rewrite`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episode_id: episode.value.id }),
    })
    if (!res.ok || !res.body) throw new Error('请求失败')
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let lastEvent = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('event: ')) { lastEvent = line.slice(7).trim(); continue }
        if (line.startsWith('data: ')) {
          try {
            const d = JSON.parse(line.slice(6))
            if (d.tool) agentEvents.value.push(`调用工具：${d.tool}`)
            if (d.text) agentEvents.value.push(d.text.slice(0, 60))
            if (agentEvents.value.length > 20) agentEvents.value.shift()
            if (lastEvent === 'done') { await load(); ElMessage.success('AI 改写完成') }
          } catch { /**/ }
        }
      }
    }
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
    runningType.value = null
  }
}

async function doExtract() {
  if (!episode.value) return
  running.value = true
  runningType.value = 'extract'
  agentEvents.value = []
  try {
    const res = await fetch(`${BASE}/agent/extract`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episode_id: episode.value.id, drama_id: dramaId }),
    })
    if (!res.ok || !res.body) throw new Error('请求失败')
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const d = JSON.parse(line.slice(6))
            if (d.tool) agentEvents.value.push(`调用工具：${d.tool}`)
            if (d.text) agentEvents.value.push(d.text.slice(0, 60))
            if (agentEvents.value.length > 20) agentEvents.value.shift()
          } catch { /**/ }
        }
      }
    }
    const [cRes, sRes] = await Promise.all([
      fetch(`${BASE}/episodes/${episode.value.id}/characters`),
      fetch(`${BASE}/episodes/${episode.value.id}/scenes`),
    ])
    chars.value = (await cRes.json()).items || []
    scenes.value = (await sRes.json()).items || []
    ElMessage.success(`提取完成：${chars.value.length} 角色，${scenes.value.length} 场景`)
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
    runningType.value = null
  }
}

async function doVoiceAssign() {
  if (!episode.value) return
  running.value = true
  runningType.value = 'voice'
  try {
    await streamAgent(`${BASE}/agent/voice`, { episode_id: episode.value.id, drama_id: dramaId }, 'voice')
    const cRes = await fetch(`${BASE}/episodes/${episode.value.id}/characters`)
    chars.value = (await cRes.json()).items || []
    ElMessage.success('音色分配完成')
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
    runningType.value = null
  }
}

async function updateCharVoice(charId: number, timbreId: number) {
  await fetch(`${BASE}/characters/${charId}/voice`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ timbre_id: timbreId }),
  })
  const c = chars.value.find(x => x.id === charId)
  if (c) c.timbre_id = timbreId
}

async function doBreakdown() {
  if (!episode.value) return
  running.value = true
  runningType.value = 'storyboard'
  agentEvents.value = []
  try {
    await streamAgent(`${BASE}/agent/storyboard`, { episode_id: episode.value.id, drama_id: dramaId }, 'storyboard')
    const sbRes = await fetch(`${BASE}/episodes/${episode.value.id}/storyboards`)
    sbs.value = (await sbRes.json()).items || []
    if (sbs.value.length) selectedSb.value = sbs.value[0]
    ElMessage.success(`分镜拆解完成：${sbs.value.length} 个镜头`)
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
    runningType.value = null
  }
}

async function addShot() {
  if (!episode.value) return
  const res = await fetch(`${BASE}/episodes/${episode.value.id}/storyboards`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ storyboard_number: sbs.value.length + 1, duration: 10 }),
  })
  const sb = await res.json()
  sbs.value.push(sb)
  selectedSb.value = sb
}

async function updateField(sb: any, field: string, value: any) {
  sb[field] = value
  await fetch(`${BASE}/storyboards/${sb.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ [field]: value }),
  })
}

async function deleteShot(sb: any) {
  await fetch(`${BASE}/storyboards/${sb.id}`, { method: 'DELETE' })
  sbs.value = sbs.value.filter(s => s.id !== sb.id)
  selectedSb.value = sbs.value[0] || null
}

onMounted(load)
</script>

<style scoped>
.studio {
  display: flex; flex-direction: column; height: 100vh;
  overflow: hidden; background: #0f0f1a;
}
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; height: 52px;
  border-bottom: 1px solid rgba(255,255,255,0.06); flex-shrink: 0;
}
.topbar-left { display: flex; align-items: center; gap: 16px; }
.back-btn {
  display: flex; align-items: center; gap: 6px;
  background: none; border: none; cursor: pointer;
  color: rgba(255,255,255,0.35); font-size: 13px; padding: 0; transition: color 0.2s;
}
.back-btn:hover { color: rgba(255,255,255,0.75); }
.studio-identity { display: flex; align-items: center; gap: 10px; }
.studio-title { font-size: 15px; font-weight: 600; color: #fff; margin: 0; }
.episode-chip {
  font-size: 11px; padding: 2px 8px; border-radius: 99px;
  background: rgba(167,139,250,0.12); color: #c4b5fd;
  border: 1px solid rgba(167,139,250,0.2);
}
.meta-inline { font-size: 12px; color: rgba(255,255,255,0.3); }
.studio-body { display: flex; flex: 1; overflow: hidden; }

/* sidebar */
.sidebar { width: 200px; flex-shrink: 0; border-right: 1px solid rgba(255,255,255,0.06); overflow-y: auto; padding: 16px 0; }
.pipe-section { margin-bottom: 20px; }
.pipe-section-label {
  font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
  color: rgba(255,255,255,0.25); text-transform: uppercase; padding: 0 16px 8px;
}
.pipe-item {
  width: 100%; display: flex; align-items: center; gap: 10px;
  padding: 8px 16px; background: none; border: none; cursor: pointer;
  text-align: left; transition: background 0.15s; border-left: 2px solid transparent;
}
.pipe-item:hover { background: rgba(255,255,255,0.04); }
.pipe-item.active { background: rgba(167,139,250,0.08); border-left-color: #a78bfa; }
.pipe-icon { width: 16px; height: 16px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,0.3); }
.pipe-item.done .pipe-icon { color: #4ade80; }
.pipe-item.active .pipe-icon { color: #a78bfa; }
.pipe-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.pipe-copy { display: flex; flex-direction: column; gap: 2px; }
.pipe-label { font-size: 13px; color: rgba(255,255,255,0.5); }
.pipe-item.active .pipe-label { color: #fff; font-weight: 500; }
.pipe-item.done .pipe-label { color: rgba(255,255,255,0.7); }
.pipe-sub { font-size: 11px; color: rgba(255,255,255,0.25); }

/* main */
.main { flex: 1; overflow-y: auto; }
.content-panel { display: flex; flex-direction: column; height: 100%; }
.panel-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 24px; border-bottom: 1px solid rgba(255,255,255,0.06); flex-shrink: 0;
}
.step-indicator { display: flex; align-items: center; gap: 8px; }
.step-num { font-size: 11px; font-weight: 700; color: #a78bfa; }
.step-name { font-size: 14px; font-weight: 600; color: #fff; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.char-count { font-size: 12px; color: rgba(255,255,255,0.35); }
.fill-textarea {
  flex: 1; width: 100%; padding: 24px; background: transparent; border: none; outline: none;
  color: rgba(255,255,255,0.85); font-size: 14px; line-height: 1.7; resize: none; font-family: inherit;
}
.fill-textarea::placeholder { color: rgba(255,255,255,0.2); }
.step-empty {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; color: rgba(255,255,255,0.3); padding: 40px;
}
.empty-title { font-size: 15px; font-weight: 600; color: rgba(255,255,255,0.7); margin: 0; }
.empty-desc { font-size: 13px; color: rgba(255,255,255,0.35); max-width: 360px; text-align: center; line-height: 1.6; margin: 0; }
.empty-actions { display: flex; gap: 10px; margin-top: 4px; }
.step-loading {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; color: rgba(255,255,255,0.5);
}
.loading-text { font-size: 14px; }
.loading-events { max-width: 400px; width: 100%; max-height: 160px; overflow: hidden; display: flex; flex-direction: column; gap: 4px; }
.event-line { font-size: 12px; color: rgba(255,255,255,0.35); font-family: monospace; }

/* card */
.card { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 20px; }
.tag { font-size: 11px; padding: 1px 6px; border-radius: 99px; background: rgba(167,139,250,0.12); color: #c4b5fd; }
.tag-success { background: rgba(74,222,128,0.12); color: #4ade80; }
.dim { color: rgba(255,255,255,0.3); }
.mono { font-family: monospace; }
.ml-auto { margin-left: auto; }

/* extract */
.extract-stage { padding: 24px; display: flex; flex-direction: row; gap: 16px; flex: 1; overflow: hidden; align-items: stretch; }
.extract-summary { width: 200px; flex-shrink: 0; display: flex; flex-direction: column; gap: 8px; }
.summary-kicker { font-size: 10px; font-weight: 600; letter-spacing: 0.1em; color: rgba(255,255,255,0.25); text-transform: uppercase; }
.summary-title { font-size: 16px; font-weight: 700; color: #fff; }
.summary-stats { display: flex; gap: 24px; }
.summary-stat { display: flex; flex-direction: column; gap: 2px; }
.summary-stat span { font-size: 12px; color: rgba(255,255,255,0.4); }
.summary-stat strong { font-size: 22px; font-weight: 700; color: #a78bfa; }
.summary-action {
  margin-top: auto; width: 100%; height: 36px; background: none; border: none;
  color: rgba(255,255,255,0.35); font-size: 13px; cursor: pointer; border-radius: 6px; transition: color 0.2s, background 0.2s;
}
.summary-action:hover { color: rgba(255,255,255,0.9); background: rgba(108,99,255,0.2); }
.extract-card { padding: 16px; flex: 1; overflow-y: auto; }
.extract-head { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.7); margin-bottom: 12px; }
.extract-list { display: flex; flex-direction: column; gap: 10px; }
.extract-row { display: flex; align-items: flex-start; gap: 10px; }
.char-avatar {
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
  background: rgba(167,139,250,0.12); color: #a78bfa;
  display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 600;
}
.scene-dot { width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0; background: rgba(74,222,128,0.1); border: 1px solid rgba(74,222,128,0.2); }
.extract-info { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.extract-name-row { display: flex; align-items: center; gap: 8px; }
.extract-name { font-size: 14px; font-weight: 600; color: #fff; }
.extract-meta { font-size: 12px; color: rgba(255,255,255,0.4); line-height: 1.5; }

/* voice */
.voice-stage { display: flex; flex-direction: row; gap: 16px; flex: 1; overflow: hidden; padding: 24px; }
.voice-sidebar { width: 220px; flex-shrink: 0; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
.voice-sidebar-kicker { font-size: 10px; font-weight: 600; letter-spacing: 0.1em; color: rgba(255,255,255,0.25); text-transform: uppercase; }
.voice-sidebar-title { font-size: 15px; font-weight: 700; color: #fff; }
.voice-sidebar-desc { font-size: 12px; color: rgba(255,255,255,0.4); line-height: 1.6; }
.voice-sidebar-stats { display: flex; gap: 16px; }
.voice-stat { display: flex; flex-direction: column; gap: 2px; }
.voice-stat span { font-size: 11px; color: rgba(255,255,255,0.4); }
.voice-stat strong { font-size: 18px; font-weight: 700; color: #a78bfa; }
.voice-lib-label { font-size: 11px; font-weight: 600; color: rgba(255,255,255,0.4); display: flex; align-items: center; gap: 6px; margin-top: 4px; }
.voice-lib { display: flex; flex-direction: column; gap: 8px; overflow-y: auto; }
.voice-lib-item { padding: 10px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; }
.voice-lib-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.voice-lib-name { font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.8); }
.voice-lib-traits { font-size: 11px; color: rgba(255,255,255,0.35); }
.voice-grid { flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; overflow-y: auto; align-content: start; }
.voice-card { display: flex; flex-direction: column; gap: 10px; padding: 16px; }
.voice-card-head { display: flex; align-items: center; gap: 10px; }
.voice-char-info { display: flex; flex-direction: column; gap: 3px; }
.voice-char-name-row { display: flex; align-items: center; gap: 8px; }
.voice-card-desc { font-size: 12px; color: rgba(255,255,255,0.4); line-height: 1.5; }
.voice-select-block { display: flex; flex-direction: column; gap: 5px; }
.voice-profile-card { padding: 10px; background: rgba(167,139,250,0.06); border: 1px solid rgba(167,139,250,0.15); border-radius: 8px; }
.voice-profile-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.voice-profile-name { font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.8); }
.voice-profile-traits { font-size: 11px; color: rgba(255,255,255,0.4); }
.voice-profile-suitable { font-size: 11px; color: rgba(167,139,250,0.7); margin-top: 2px; }

/* storyboard split layout */
.split-layout { display: flex; flex: 1; overflow: hidden; }
.shot-list { width: 260px; flex-shrink: 0; border-right: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; overflow: hidden; }
.shot-list-head { display: flex; align-items: flex-start; justify-content: space-between; padding: 16px; border-bottom: 1px solid rgba(255,255,255,0.06); }
.shot-list-title { font-size: 13px; font-weight: 600; color: #fff; }
.shot-list-sub { font-size: 11px; color: rgba(255,255,255,0.3); margin-top: 2px; }
.shot-list-body { flex: 1; overflow-y: auto; }
.shot-item { padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.04); cursor: pointer; transition: background 0.15s; }
.shot-item:hover { background: rgba(255,255,255,0.03); }
.shot-item.active { background: rgba(167,139,250,0.08); border-left: 2px solid #a78bfa; }
.shot-item-header { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.shot-num { font-size: 11px; font-weight: 700; color: #a78bfa; font-family: monospace; }
.shot-status { display: flex; gap: 4px; margin-left: auto; }
.shot-dot { width: 6px; height: 6px; border-radius: 50%; }
.shot-dot.has-img { background: #a78bfa; }
.shot-dot.has-video { background: #4ade80; }
.shot-dot.has-dialogue { background: #fbbf24; }
.shot-body { margin-bottom: 4px; }
.shot-desc { font-size: 12px; color: rgba(255,255,255,0.6); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.shot-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.shot-location { font-size: 10px; color: rgba(255,255,255,0.3); background: rgba(255,255,255,0.05); padding: 1px 5px; border-radius: 4px; }
.shot-dialogue { font-size: 10px; color: rgba(251,191,36,0.6); }

/* detail panel */
.detail-panel { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }
.detail-empty { align-items: center; justify-content: center; color: rgba(255,255,255,0.3); font-size: 13px; }
.detail-head {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 24px; border-bottom: 1px solid rgba(255,255,255,0.06); flex-shrink: 0;
}
.detail-head-copy { display: flex; flex-direction: column; gap: 2px; }
.detail-head-title { font-size: 13px; font-weight: 700; color: #fff; }
.detail-head-sub { font-size: 11px; color: rgba(255,255,255,0.4); }
.detail-body { padding: 24px; display: flex; flex-direction: column; gap: 24px; }
.detail-section { display: flex; flex-direction: column; gap: 12px; }
.detail-section-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 4px; }
.detail-section-title { font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.8); }
.detail-section-copy { font-size: 11px; color: rgba(255,255,255,0.3); }

/* form fields */
.field { display: flex; flex-direction: column; gap: 5px; }
.field-label { font-size: 11px; color: rgba(255,255,255,0.4); font-weight: 500; }
.field-grid { display: grid; gap: 12px; }
.field-grid-2 { grid-template-columns: 1fr 1fr; }
.field-grid-4 { grid-template-columns: repeat(4, 1fr); }
.input, .input-select {
  background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
  border-radius: 6px; padding: 7px 10px; color: rgba(255,255,255,0.85);
  font-size: 13px; outline: none; width: 100%; transition: border-color 0.2s; font-family: inherit;
}
.input:focus, .input-select:focus { border-color: rgba(167,139,250,0.4); }
.input-select { cursor: pointer; }
.input-select option { background: #1a1a2e; }
.textarea {
  background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
  border-radius: 6px; padding: 8px 10px; color: rgba(255,255,255,0.85);
  font-size: 13px; outline: none; width: 100%; resize: vertical; font-family: inherit; transition: border-color 0.2s;
}
.textarea:focus { border-color: rgba(167,139,250,0.4); }
.role-pills { display: flex; flex-wrap: wrap; gap: 6px; }
.role-pill {
  padding: 3px 10px; border-radius: 99px; font-size: 12px; cursor: pointer;
  background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.5); transition: all 0.15s;
}
.role-pill.active { background: rgba(167,139,250,0.15); border-color: rgba(167,139,250,0.4); color: #c4b5fd; }
.role-pill:hover { background: rgba(255,255,255,0.08); }

/* buttons */
.btn-sm {
  display: flex; align-items: center; gap: 5px;
  background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.7);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
  padding: 5px 12px; font-size: 12px; cursor: pointer; transition: background 0.2s; white-space: nowrap;
}
.btn-sm:hover { background: rgba(255,255,255,0.1); }
.btn-sm:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-sm.btn-accent { background: rgba(167,139,250,0.12); border-color: rgba(167,139,250,0.2); color: #c4b5fd; }
.btn-sm.btn-accent:hover { background: rgba(167,139,250,0.2); }
.btn-sm.btn-danger { background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.2); color: rgba(239,68,68,0.7); }
.btn-sm.btn-danger:hover { background: rgba(239,68,68,0.15); }
.btn-primary {
  display: flex; align-items: center; gap: 6px;
  background: #7c3aed; color: #fff; border: none;
  border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: background 0.2s;
}
.btn-primary:hover { background: #6d28d9; }
.btn-ghost {
  background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.7);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
  padding: 8px 16px; font-size: 13px; cursor: pointer;
}
.btn-ghost:hover { background: rgba(255,255,255,0.1); }

.loading-full { display: flex; align-items: center; justify-content: center; height: 100%; color: rgba(255,255,255,0.4); }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 制作面板通用 */
.prod-scroll { flex: 1; overflow-y: auto; padding: 24px; }
.asset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.asset-card { display: flex; flex-direction: column; gap: 0; overflow: hidden; padding: 0; }
.asset-cover { position: relative; width: 100%; aspect-ratio: 1; background: rgba(255,255,255,0.03); overflow: hidden; }
.asset-cover.wide { aspect-ratio: 16/9; }
.asset-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.asset-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,0.15); }
.asset-initial { font-size: 32px; font-weight: 700; color: rgba(167,139,250,0.3); }
.asset-badge {
  position: absolute; top: 8px; right: 8px;
  font-size: 10px; padding: 2px 7px; border-radius: 99px;
  background: rgba(0,0,0,0.6); color: rgba(255,255,255,0.4);
}
.asset-badge.badge-ok { background: rgba(74,222,128,0.15); color: #4ade80; }
.asset-body { padding: 10px 12px 6px; display: flex; flex-direction: column; gap: 3px; }
.asset-name { font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.85); }
.asset-meta { font-size: 11px; }
.asset-desc { font-size: 11px; line-height: 1.5; margin-top: 2px; }
.asset-foot { padding: 6px 12px 12px; display: flex; align-items: center; gap: 6px; }

.dot { width: 6px; height: 6px; border-radius: 50%; background: rgba(255,255,255,0.15); flex-shrink: 0; display: inline-block; }
.dot.ok { background: #4ade80; }
.dot.pending { background: #facc15; }

/* 配音 */
.dub-grid { display: flex; flex-direction: column; gap: 10px; }
.dub-card { padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; }
.dub-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.dub-copy { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.dub-title { display: flex; align-items: center; gap: 6px; }
.frame-num { font-size: 11px; font-weight: 700; color: #a78bfa; font-family: monospace; }
.frame-badge { font-size: 11px; color: rgba(255,255,255,0.5); background: rgba(255,255,255,0.06); padding: 1px 7px; border-radius: 99px; }
.dub-desc { font-size: 13px; color: rgba(255,255,255,0.75); line-height: 1.5; }
.dub-meta { display: flex; gap: 10px; }
.dub-meta .dim { font-size: 11px; }
.dub-foot { display: flex; align-items: center; gap: 10px; }
.dub-audio { flex: 1; height: 32px; }

/* 镜头图片行布局 */
.frame-mode-toggle { display: flex; gap: 2px; background: rgba(255,255,255,0.06); border-radius: 8px; padding: 2px; }
.frame-mode-toggle .btn-sm { border-radius: 6px; border: none; background: transparent; color: rgba(255,255,255,0.45); padding: 3px 10px; font-size: 11px; cursor: pointer; transition: all 0.15s; }
.frame-mode-toggle .btn-sm.active { background: rgba(124,58,237,0.5); color: #fff; }
.frame-mode-toggle .btn-sm:hover:not(.active) { color: rgba(255,255,255,0.7); }
.shot-frame-scroll { flex: 1; overflow-y: auto; padding: 10px 16px; }
.shot-frame-grid { display: flex; flex-direction: column; gap: 8px; }
.shot-frame-row {
  display: flex; align-items: center; gap: 14px;
  padding: 12px 14px; cursor: default;
  border-radius: 10px;
  border: 1.5px solid transparent;
}
.shot-frame-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.shot-frame-top { display: flex; align-items: center; gap: 8px; }
.shot-frame-desc { font-size: 13px; color: rgba(255,255,255,0.7); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.shot-frame-meta { display: flex; align-items: center; gap: 6px; }
.shot-frame-thumbs { display: flex; gap: 8px; flex-shrink: 0; }
.shot-frame-thumb-wrap { display: flex; flex-direction: column; gap: 3px; align-items: center; }
.shot-frame-label { font-size: 10px; font-weight: 600; color: rgba(255,255,255,0.3); }
.shot-frame-thumb {
  position: relative; width: 112px; height: 63px;
  border-radius: 6px; overflow: hidden; cursor: pointer;
  background: rgba(255,255,255,0.04);
  border: 1.5px solid rgba(255,255,255,0.08);
  transition: border-color 0.15s;
}
.shot-frame-thumb:hover { border-color: #7c3aed; }
.shot-frame-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.shot-frame-empty { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,0.2); }
.shot-frame-re {
  display: none; position: absolute; bottom: 4px; right: 4px;
  width: 18px; height: 18px; border-radius: 4px;
  background: rgba(0,0,0,0.6); align-items: center; justify-content: center;
  color: rgba(255,255,255,0.7);
}
.shot-frame-thumb:hover .shot-frame-re { display: flex; }

/* 镜头图/视频/合成 */
.prod-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.prod-card { display: flex; flex-direction: column; gap: 0; overflow: hidden; padding: 0; }
.prod-cover { position: relative; width: 100%; aspect-ratio: 16/9; background: rgba(255,255,255,0.03); overflow: hidden; }
.prod-cover-empty { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,0.15); }
.prod-video { width: 100%; height: 100%; object-fit: cover; }
.prod-idx { position: absolute; top: 6px; left: 8px; font-size: 10px; font-weight: 700; color: rgba(255,255,255,0.5); font-family: monospace; }
.prod-overlay-badge { position: absolute; top: 6px; right: 8px; font-size: 10px; padding: 1px 6px; border-radius: 99px; background: rgba(74,222,128,0.2); color: #4ade80; }
.prod-info { padding: 8px 10px 10px; display: flex; flex-direction: column; gap: 4px; }
.prod-desc { font-size: 12px; color: rgba(255,255,255,0.7); }
.prod-meta-line { font-size: 10px; color: rgba(255,255,255,0.3); }
.prod-dots { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 导出 */
.export-body { flex: 1; display: flex; align-items: flex-start; padding: 24px; }
.export-card { max-width: 480px; width: 100%; display: flex; flex-direction: column; gap: 12px; }
.export-kicker { font-size: 10px; font-weight: 600; letter-spacing: 0.1em; color: rgba(255,255,255,0.25); text-transform: uppercase; }
.export-title { font-size: 20px; font-weight: 700; color: #fff; }
.export-desc { font-size: 13px; color: rgba(255,255,255,0.4); line-height: 1.6; }
.export-stats { display: flex; gap: 24px; margin: 4px 0; }
.export-stat { display: flex; flex-direction: column; gap: 2px; }
.export-stat span { font-size: 11px; color: rgba(255,255,255,0.4); }
.export-stat strong { font-size: 22px; font-weight: 700; color: #a78bfa; }
.export-video-wrap { margin-top: 8px; }
.export-video { width: 100%; border-radius: 8px; }
.export-empty { padding: 24px 0; }
</style>
