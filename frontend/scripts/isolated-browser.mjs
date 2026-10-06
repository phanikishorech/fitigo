// Each fixture suite gets separate storage now that production cross-tab logout
// intentionally propagates authentication changes between tabs.
export async function isolatedBrowserTarget(debug = 'http://localhost:9231') {
  const info = await (await fetch(`${debug}/json/version`)).json()
  const ws = new WebSocket(info.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  let sequence = 0
  const pending = new Map()
  ws.onmessage = event => {
    const message = JSON.parse(event.data), item = pending.get(message.id)
    if (!item) return
    pending.delete(message.id); clearTimeout(item.timer)
    message.error ? item.reject(new Error(message.error.message)) : item.resolve(message.result)
  }
  function command(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++sequence, timer = setTimeout(() => reject(new Error(`Browser timeout: ${method}`)), 15000)
      pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params }))
    })
  }
  const { browserContextId } = await command('Target.createBrowserContext')
  const { targetId } = await command('Target.createTarget', { url: 'about:blank', browserContextId })
  const target = (await (await fetch(`${debug}/json`)).json()).find(item => item.id === targetId)
  return { ...target, dispose: async () => { await command('Target.disposeBrowserContext', { browserContextId }); ws.close() } }
}