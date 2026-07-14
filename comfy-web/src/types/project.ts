export interface ProjectCoverAsset { id:number;location:string;asset_type?:'picture'|'video';created_at?:string }
export interface ProjectSummary { id:number;name:string;asset_count?:number;scope?:'personal'|'shared';role?:'owner'|'editor'|'viewer';member_count?:number;updated_at?:string;cover_assets?:ProjectCoverAsset[] }
