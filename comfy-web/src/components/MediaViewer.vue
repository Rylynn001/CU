<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

export interface MediaViewerItem { id?:number|string; src:string; type:'image'|'video'; title?:string; subtitle?:string }
const props=withDefaults(defineProps<{visible:boolean;item:MediaViewerItem|null;showNav?:boolean}>(),{showNav:false})
const emit=defineEmits<{close:[];prev:[];next:[];download:[MediaViewerItem]}>()
const video=ref<HTMLVideoElement|null>(null), zoomed=ref(false)
watch(()=>props.item?.src,()=>{zoomed.value=false;video.value?.load()})
watch(()=>props.visible,value=>{if(!value)video.value?.pause()})
function close(){video.value?.pause();emit('close')}
function download(){if(!props.item)return;emit('download',props.item);const link=document.createElement('a');link.href=props.item.src;link.download=props.item.title||'media';link.click()}
function keydown(event:KeyboardEvent){if(!props.visible)return;if(event.key==='Escape')close();else if(event.key==='ArrowLeft'&&props.showNav)emit('prev');else if(event.key==='ArrowRight'&&props.showNav)emit('next');else if(event.code==='Space'&&props.item?.type==='video'){event.preventDefault();if(video.value)video.value.paused?video.value.play():video.value.pause()}}
onMounted(()=>window.addEventListener('keydown',keydown));onBeforeUnmount(()=>window.removeEventListener('keydown',keydown))
</script>

<template>
  <Teleport to="body">
    <Transition name="media-fade">
      <div v-if="visible&&item" class="media-overlay" role="dialog" aria-modal="true" :aria-label="item.title||'媒体预览'" @mousedown.self="close">
        <header><div><strong>{{item.title||'未命名素材'}}</strong><span v-if="item.subtitle">{{item.subtitle}}</span></div><nav><button title="下载" @click="download">下载</button><button class="close" title="关闭" @click="close">×</button></nav></header>
        <button v-if="showNav" class="arrow prev" aria-label="上一个" @click="emit('prev')">‹</button>
        <main :class="{zoomed}">
          <img v-if="item.type==='image'" :src="item.src" :alt="item.title" draggable="false" @dblclick="zoomed=!zoomed" />
          <video v-else ref="video" :src="item.src" controls autoplay playsinline />
        </main>
        <button v-if="showNav" class="arrow next" aria-label="下一个" @click="emit('next')">›</button>
        <footer>{{item.type==='image'?'双击切换原尺寸':'空格键播放 / 暂停'}}<span>ESC 关闭</span></footer>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.media-overlay{position:fixed;inset:0;z-index:9500;display:grid;grid-template:54px minmax(0,1fr) 34px/72px minmax(0,1fr) 72px;background:rgba(1,3,7,.92);backdrop-filter:blur(18px);color:var(--color-text)}header{grid-column:1/-1;padding:0 20px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,.08)}header>div{min-width:0;display:flex;align-items:baseline;gap:10px}header strong{overflow:hidden;font-size:13px;font-weight:500;text-overflow:ellipsis;white-space:nowrap}header span{color:var(--color-faint);font-size:10px}nav{display:flex;align-items:center;gap:4px}button{border:0;background:transparent;color:var(--color-muted);cursor:pointer}nav button{height:32px;padding:0 10px;border-radius:6px;font-size:11px}nav button:hover{background:rgba(255,255,255,.07);color:var(--color-text)}nav .close{width:32px;padding:0;font-size:20px}main{grid-column:2;min-width:0;min-height:0;display:flex;align-items:center;justify-content:center;overflow:auto;padding:20px;box-sizing:border-box}main img,main video{display:block;max-width:100%;max-height:100%;object-fit:contain;border-radius:5px;box-shadow:0 18px 60px rgba(0,0,0,.32)}main img{cursor:zoom-in;user-select:none}main.zoomed{align-items:flex-start;justify-content:flex-start}main.zoomed img{max-width:none;max-height:none;width:auto;height:auto;cursor:zoom-out}.arrow{align-self:center;width:42px;height:64px;border-radius:7px;font-size:34px}.arrow:hover{background:rgba(255,255,255,.06);color:#fff}.prev{grid-column:1;grid-row:2;justify-self:center}.next{grid-column:3;grid-row:2;justify-self:center}footer{grid-column:1/-1;padding:0 20px;display:flex;align-items:center;justify-content:center;gap:18px;color:var(--color-faint);font-size:9px}footer span{opacity:.65}.media-fade-enter-active,.media-fade-leave-active{transition:opacity .18s ease}.media-fade-enter-from,.media-fade-leave-to{opacity:0}
@media(max-width:700px){.media-overlay{grid-template:48px minmax(0,1fr) 30px/42px minmax(0,1fr) 42px}header{padding:0 10px}main{padding:8px}.arrow{width:34px}.media-overlay:not(:has(.arrow)){grid-template-columns:0 minmax(0,1fr) 0}}
</style>
