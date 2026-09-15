import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'

// When the repo is opened via a symlink/junction (e.g. in a tooling workspace),
// `process.cwd()` can be the symlinked path while node_modules resolves to the real path.
// Vite's dependency optimizer can crash when those paths get mixed.
//
// Run Vite with `cwd` set to the real path to keep all internal paths consistent.
const realCwd = fs.realpathSync(process.cwd())
const viteBin = path.join(realCwd, 'node_modules', 'vite', 'bin', 'vite.js')

const args = process.argv.slice(2)

const child = spawn(process.execPath, [viteBin, ...args], {
  cwd: realCwd,
  stdio: 'inherit',
  env: process.env
})

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal)
  process.exit(code ?? 0)
})

child.on('error', (err) => {
  console.error(err)
  process.exit(1)
})
