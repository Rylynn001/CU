<script setup lang="ts">
import type { ProjectCoverAsset,ProjectSummary } from '../types/project'
const props=defineProps<{project:ProjectSummary;fallbackAssets?:ProjectCoverAsset[]}>()
defineEmits<{open:[number]}>()
const url=(location:string)=>/^https?:\/\//.test(location)?location:`/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
const covers=()=>props.project.cover_assets?.length?props.project.cover_assets.slice(0,3):(props.fallbackAssets||[]).slice(0,3)
const updated=()=>props.project.updated_at?new Date(props.project.updated_at).toLocaleDateString('zh-CN',{month:'numeric',day:'numeric'}):''
</script>
<template>
  <article class="project-card" tabindex="0" @click="$emit('open',project.id)" @keyup.enter="$emit('open',project.id)">
    <div class="cover" :class="`count-${covers().length}`">
      <template v-if="covers().length"><div v-for="asset in covers()" :key="asset.id" class="tile"><video v-if="asset.asset_type==='video'" :src="url(asset.location)" muted preload="metadata" /><img v-else :src="url(asset.location)" alt="" /></div></template>
      <div v-else class="empty"><span>{{project.name.slice(0,1).toUpperCase()}}</span></div>
    </div>
    <div class="project-info"><div><strong>{{project.name}}</strong><span>{{project.asset_count||0}} 项素材</span></div><small>{{project.scope==='shared'?`团队共享 · ${project.member_count||1} 人`:'我的项目'}}<template v-if="updated()"> · {{updated()}}</template></small></div>
  </article>
</template>
<style scoped>
.project-card{position:relative;aspect-ratio:16/9;min-width:0;overflow:hidden;border-radius:8px;background:rgba(12,16,22,.5);cursor:pointer;outline:0}.cover{position:absolute;inset:0;display:grid;gap:2px}.cover.count-2,.cover.count-3{grid-template-columns:2fr 1fr}.cover.count-3 .tile:first-child{grid-row:1/3}.tile{min-width:0;min-height:0;overflow:hidden}.tile img,.tile video{width:100%;height:100%;display:block;object-fit:cover;filter:brightness(.78) saturate(.88);transition:filter .22s,transform .3s}.project-card:hover .tile img,.project-card:hover .tile video,.project-card:focus .tile img,.project-card:focus .tile video{filter:brightness(.92) saturate(.98);transform:scale(1.015)}.empty{display:grid;place-items:center;background:linear-gradient(145deg,rgba(166,231,226,.07),rgba(255,255,255,.015))}.empty span{color:rgba(255,255,255,.13);font-size:40px}.project-info{position:absolute;z-index:2;inset:auto 0 0;padding:42px 13px 12px;display:flex;align-items:end;justify-content:space-between;gap:12px;background:linear-gradient(transparent,rgba(3,5,9,.88));opacity:0;transform:translateY(5px);transition:opacity .2s,transform .2s}.project-card:hover .project-info,.project-card:focus .project-info{opacity:1;transform:none}.project-info>div{min-width:0}.project-info strong{display:block;overflow:hidden;color:#fff;font-size:13px;font-weight:550;text-overflow:ellipsis;white-space:nowrap}.project-info span,.project-info small{color:rgba(255,255,255,.5);font-size:9px}.project-info span{display:block;margin-top:5px}.project-info small{white-space:nowrap}@media(max-width:760px){.project-info{opacity:1;transform:none}}
</style>
