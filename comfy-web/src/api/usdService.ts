const BASE = '/api/api-proxy/usd'
export interface UsdPrimNode { path:string;name:string;type:string;active:boolean;loaded:boolean;has_payload:boolean;visible?:boolean;transform?:number[];variants:Record<string,{selection:string;options:string[]}>;children:UsdPrimNode[] }
export interface UsdStageDetail { stage:any;prims:UsdPrimNode[];cameras:string[];lights:string[];layers:string[];up_axis:string;meters_per_unit:number;composition_errors:string[] }
async function json(response:Response){if(!response.ok)throw new Error(await response.text());return response.json()}
export async function getUsdCapabilities(){return json(await fetch(`${BASE}/capabilities`)) as Promise<{openusd:boolean;formats:string[]}>}
export async function createUsdStage(files:File[],userId:number,projectId:number,rootFile?:string,name?:string){const body=new FormData();files.forEach(file=>body.append('files',file));body.append('user_id',String(userId));body.append('project_id',String(projectId));if(rootFile)body.append('root_file',rootFile);if(name)body.append('name',name);return json(await fetch(`${BASE}/stages`,{method:'POST',body})) as Promise<{id:number;name:string}>}
export async function getUsdStage(id:number,userId:number){return json(await fetch(`${BASE}/stages/${id}?user_id=${userId}`)) as Promise<UsdStageDetail>}
export async function listUsdStages(userId:number,projectId:number){const data=await json(await fetch(`${BASE}/stages?user_id=${userId}&project_id=${projectId}`));return data.stages||[]}
export async function saveUsdSession(id:number,userId:number,state:Record<string,unknown>){await json(await fetch(`${BASE}/stages/${id}/session?user_id=${userId}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(state)}))}
export const usdPreviewUrl=(id:number,userId:number)=>`${BASE}/stages/${id}/preview?user_id=${userId}`
export const usdExportUrl=(id:number,userId:number,type:'usdz'|'session')=>`${BASE}/stages/${id}/export/${type}?user_id=${userId}`
