<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface PromptItem { id:string; title:string; prompt:string; negative:string; type:'image'|'video'; tags:string[]; favorite:boolean; updatedAt:number }
const props=defineProps<{type:'image'|'video';prompt:string;negative?:string}>()
const emit=defineEmits<{select:[PromptItem]}>()
const open=ref(false), query=ref(''), filter=ref<'all'|'image'|'video'|'favorite'>('all'), editing=ref<PromptItem|null>(null)
const userId=(()=>{try{return JSON.parse(localStorage.getItem('user')||'null')?.id||'debug'}catch{return'debug'}})()
const key=`prompt-library:${userId}`
const items=ref<PromptItem[]>([])
function load(){try{items.value=JSON.parse(localStorage.getItem(key)||'[]')}catch{items.value=[]}}
function persist(){localStorage.setItem(key,JSON.stringify(items.value))}
watch(open,value=>{if(value)load()})
const visible=computed(()=>items.value.filter(item=>{
  const matchFilter=filter.value==='all'||filter.value==='favorite'&&item.favorite||item.type===filter.value
  const text=`${item.title} ${item.prompt} ${item.tags.join(' ')}`.toLowerCase()
  return matchFilter&&text.includes(query.value.trim().toLowerCase())
}).sort((a,b)=>Number(b.favorite)-Number(a.favorite)||b.updatedAt-a.updatedAt))
function draft():PromptItem{return{id:crypto.randomUUID(),title:'',prompt:props.prompt,negative:props.negative||'',type:props.type,tags:[],favorite:false,updatedAt:Date.now()}}
function save(){if(!editing.value?.title.trim()||!editing.value.prompt.trim())return;const index=items.value.findIndex(i=>i.id===editing.value!.id);editing.value.updatedAt=Date.now();if(index<0)items.value.unshift({...editing.value});else items.value[index]={...editing.value};persist();editing.value=null}
function remove(id:string){items.value=items.value.filter(i=>i.id!==id);persist()}
function toggle(item:PromptItem){item.favorite=!item.favorite;item.updatedAt=Date.now();persist()}
function use(item:PromptItem){emit('select',item);open.value=false}
function tagText(item:PromptItem){return item.tags.join('、')}
function updateTags(value:string){if(editing.value)editing.value.tags=value.split(/[、,，\s]+/).map(v=>v.trim()).filter(Boolean).slice(0,8)}
</script>

<template>
  <button type="button" class="library-trigger" @click="open=true"><span>⌘</span> 提示词库</button>
  <Teleport to="body">
    <Transition name="prompt-fade">
      <div v-if="open" class="prompt-overlay" @mousedown.self="open=false">
        <section class="prompt-window">
          <header><div><strong>提示词库</strong><span>保存灵感，随时复用</span></div><button @click="open=false">×</button></header>
          <div class="prompt-tools">
            <input v-model="query" placeholder="搜索名称、提示词或标签" />
            <nav><button v-for="item in [{k:'all',n:'全部'},{k:'image',n:'图片'},{k:'video',n:'视频'},{k:'favorite',n:'收藏'}]" :key="item.k" :class="{active:filter===item.k}" @click="filter=item.k as any">{{item.n}}</button></nav>
            <button class="save-current" :disabled="!prompt.trim()" @click="editing=draft()">+ 保存当前提示词</button>
          </div>
          <main v-if="visible.length" class="prompt-list">
            <article v-for="item in visible" :key="item.id">
              <div class="item-copy"><div><strong>{{item.title}}</strong><span>{{item.type==='image'?'图片':'视频'}}</span></div><p>{{item.prompt}}</p><small v-if="item.tags.length">{{tagText(item)}}</small></div>
              <div class="item-actions"><button title="收藏" :class="{favorite:item.favorite}" @click="toggle(item)">☆</button><button @click="editing={...item,tags:[...item.tags]}">编辑</button><button @click="use(item)">使用</button></div>
            </article>
          </main>
          <div v-else class="prompt-empty"><strong>{{items.length?'没有匹配的提示词':'还没有保存提示词'}}</strong><span>在生成页写好提示词后，点击“保存当前提示词”。</span></div>
          <div v-if="editing" class="editor">
            <div class="editor-head"><strong>{{items.some(i=>i.id===editing?.id)?'编辑提示词':'保存提示词'}}</strong><button @click="editing=null">×</button></div>
            <label><span>名称</span><input v-model="editing.title" maxlength="40" placeholder="例如：电影感人物肖像" /></label>
            <label><span>类型</span><select v-model="editing.type"><option value="image">图片</option><option value="video">视频</option></select></label>
            <label><span>提示词</span><textarea v-model="editing.prompt" rows="6" /></label>
            <label><span>反向提示词</span><textarea v-model="editing.negative" rows="2" placeholder="可选" /></label>
            <label><span>标签</span><input :value="tagText(editing)" placeholder="人像、电影、夜景" @input="updateTags(($event.target as HTMLInputElement).value)" /></label>
            <footer><button class="delete" v-if="items.some(i=>i.id===editing?.id)" @click="remove(editing.id);editing=null">删除</button><button @click="editing=null">取消</button><button class="confirm" @click="save">保存</button></footer>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.library-trigger{height:28px;padding:0 9px;display:inline-flex;align-items:center;gap:6px;border:0;border-radius:6px;background:transparent;color:var(--color-muted);font-size:11px;cursor:pointer}.library-trigger:hover{background:rgba(255,255,255,.055);color:var(--color-text)}.library-trigger span{color:var(--color-primary)}
.prompt-overlay{position:fixed;inset:0;z-index:9000;display:grid;place-items:center;padding:28px;background:rgba(0,0,0,.55);backdrop-filter:blur(8px)}.prompt-window{position:relative;width:min(900px,94vw);height:min(680px,88vh);display:grid;grid-template-rows:58px auto 1fr;overflow:hidden;border:1px solid var(--color-border);border-radius:10px;background:#090c12;box-shadow:0 30px 90px rgba(0,0,0,.6)}header{padding:0 18px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--color-border)}header>div{display:flex;align-items:baseline;gap:10px}header strong{font-size:14px}header span{color:var(--color-faint);font-size:10px}header button,.editor-head button{border:0;background:transparent;color:var(--color-muted);font-size:20px;cursor:pointer}.prompt-tools{padding:14px 18px;display:grid;grid-template-columns:minmax(180px,1fr) auto auto;gap:12px;border-bottom:1px solid rgba(255,255,255,.07)}input,textarea,select{box-sizing:border-box;border:1px solid var(--color-border);border-radius:6px;background:rgba(255,255,255,.035);color:var(--color-text);font:inherit;outline:0}.prompt-tools>input{height:34px;padding:0 11px}.prompt-tools nav{display:flex;align-items:center;gap:2px}.prompt-tools nav button{height:30px;padding:0 9px;border:0;border-radius:5px;background:transparent;color:var(--color-muted);font-size:11px;cursor:pointer}.prompt-tools nav button.active{color:var(--color-text);background:rgba(255,255,255,.07)}.save-current,.confirm{border:1px solid rgba(166,231,226,.32)!important;background:rgba(166,231,226,.1)!important;color:var(--color-primary-strong)!important}.save-current{height:34px;padding:0 12px;border-radius:6px;font-size:11px;cursor:pointer}.save-current:disabled{opacity:.35;cursor:not-allowed}.prompt-list{overflow:auto;padding:0 18px}.prompt-list article{min-height:92px;padding:16px 2px;display:flex;align-items:center;justify-content:space-between;gap:20px;border-bottom:1px solid rgba(255,255,255,.07)}.item-copy{min-width:0}.item-copy>div{display:flex;align-items:center;gap:8px}.item-copy strong{font-size:13px;font-weight:500}.item-copy>div span{padding:2px 5px;border:1px solid var(--color-border);border-radius:4px;color:var(--color-faint);font-size:9px}.item-copy p{max-width:610px;margin:8px 0 0;overflow:hidden;color:var(--color-muted);font-size:11px;line-height:1.6;white-space:nowrap;text-overflow:ellipsis}.item-copy small{display:block;margin-top:6px;color:var(--color-faint);font-size:9px}.item-actions{display:flex;gap:5px}.item-actions button,.editor footer button{height:30px;padding:0 9px;border:1px solid var(--color-border);border-radius:5px;background:transparent;color:var(--color-muted);font-size:10px;cursor:pointer}.item-actions button:hover{color:var(--color-text)}.item-actions .favorite{color:#f0c96b}.prompt-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;color:var(--color-muted)}.prompt-empty strong{font-size:13px;font-weight:500}.prompt-empty span{color:var(--color-faint);font-size:10px}.editor{position:absolute;inset:58px 0 0 auto;width:min(390px,90vw);padding:18px;box-sizing:border-box;overflow:auto;border-left:1px solid var(--color-border);background:#0c0f16;box-shadow:-24px 0 60px rgba(0,0,0,.35)}.editor-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}.editor-head strong{font-size:14px}.editor label{display:grid;grid-template-columns:72px 1fr;align-items:start;gap:10px;margin-bottom:13px}.editor label span{padding-top:8px;color:var(--color-muted);font-size:10px}.editor input,.editor select{height:34px;padding:0 9px}.editor textarea{padding:9px;resize:vertical;line-height:1.6}.editor footer{display:flex;justify-content:flex-end;gap:7px;margin-top:18px}.editor footer .delete{margin-right:auto;color:var(--color-danger)}.prompt-fade-enter-active,.prompt-fade-leave-active{transition:opacity .16s}.prompt-fade-enter-from,.prompt-fade-leave-to{opacity:0}
@media(max-width:700px){.prompt-overlay{padding:0}.prompt-window{width:100vw;height:100vh;border:0;border-radius:0}.prompt-tools{grid-template-columns:1fr auto}.prompt-tools nav{grid-column:1/-1;overflow-x:auto;order:3}.editor{inset:58px 0 0;width:100%}.prompt-list article{align-items:flex-start}.item-actions{flex-direction:column}}
</style>
