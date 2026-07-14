interface RenderJob {
  key: string
  priority: number
  run: () => Promise<void>
}

const pending = new Map<string, RenderJob>()
let running = false
let scheduled = false

function scheduleNext() {
  if (running || scheduled || !pending.size) return
  scheduled = true
  const priority = Math.min(...[...pending.values()].map(job => job.priority))
  const start = () => {
    scheduled = false
    void runNext()
  }
  if (priority <= 1) requestAnimationFrame(start)
  else if ('requestIdleCallback' in window) window.requestIdleCallback(start, { timeout: 240 })
  else window.setTimeout(start, 32)
}

async function runNext() {
  if (running || !pending.size) return
  running = true
  try {
    const job = [...pending.values()].sort((a, b) => a.priority - b.priority)[0]
    pending.delete(job.key)
    await job.run()
  } finally {
    running = false
    if (pending.size) window.setTimeout(scheduleNext, 24)
  }
}

export function enqueueLayerRender(job: RenderJob) {
  pending.set(job.key, job)
  scheduleNext()
}

export function cancelLayerRender(key: string) {
  pending.delete(key)
}
