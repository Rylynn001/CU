-- 为已存在的 GPT Image 模型补充比例参数。
-- OpenAI Images API 最终使用 size，worker 会把比例转换为对应尺寸。
UPDATE api_models
SET parameters = '{"version":1,"fields":[{"key":"aspect_ratio","label":"比例","type":"select","default":"1:1","options":["1:1","16:9","9:16","auto"]},{"key":"quality","label":"质量","type":"select","default":"auto","options":["low","medium","high","auto"]},{"key":"n","label":"数量","type":"number","default":1,"min":1,"max":10,"step":1},{"key":"background","label":"背景","type":"select","default":"auto","options":["auto","opaque","transparent"]},{"key":"output_format","label":"输出格式","type":"select","default":"png","options":["png","jpeg","webp"]},{"key":"output_compression","label":"压缩质量","type":"number","default":100,"min":0,"max":100,"step":1}],"references":{"images":{"supported":true,"max":6},"videos":{"supported":false,"max":0}}}'
WHERE name = 'gpt-image-2';

UPDATE api_models
SET parameters = '{"version":1,"fields":[{"key":"aspect_ratio","label":"比例","type":"select","default":"1:1","options":["1:1","16:9","9:16","auto"]},{"key":"quality","label":"质量","type":"select","default":"auto","options":["low","medium","high","xhigh","max","auto"]},{"key":"n","label":"数量","type":"number","default":1,"min":1,"max":10,"step":1},{"key":"background","label":"背景","type":"select","default":"auto","options":["auto","opaque","transparent"]},{"key":"output_format","label":"输出格式","type":"select","default":"png","options":["png","jpeg","webp"]},{"key":"output_compression","label":"压缩质量","type":"number","default":100,"min":0,"max":100,"step":1}],"references":{"images":{"supported":true,"max":16},"videos":{"supported":false,"max":0}}}'
WHERE name = 'gpt-image-2.5';
