#!/usr/bin/env node
// Ultraviolet serial bridge: reads an ESP32 soil-sensor node (or gateway) over USB and
// posts each reading to the app. No npm dependencies (uses `stty` + the device file).
//
//   node hardware/bridge/serial-bridge.mjs                       # auto-detect port, post to localhost:5173
//   node hardware/bridge/serial-bridge.mjs --port /dev/cu.usbserial-0001 --baud 115200 --app http://localhost:5173
//
// Recognised firmware lines (anything else is echoed for debugging):
//   [Node node-001] raw_AO=4095  soil=0.0%  wet=NO  DO=HIGH(dry)
//   [Node node-001] Send OK  next in 30s
//   {"nodeId":"node-002","soilPct":41.2,"rawAo":2310}            (JSON per line, e.g. from a gateway)

import { spawn } from 'node:child_process';
import { openSync, readdirSync } from 'node:fs';

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, all) => (value.startsWith('--') ? [...pairs, [value.slice(2), all[index + 1]]] : pairs), []));
const app = (args.app ?? process.env.ULTRAVIOLET_URL ?? 'http://localhost:5173').replace(/\/$/, '');
const baud = Number(args.baud ?? 115200);
const port = args.port ?? autodetect();
if (!port) { console.error('No USB serial port found. Plug in the ESP32 or pass --port /dev/cu.usbserial-XXXX'); process.exit(1); }

function autodetect() {
  try {
    const ports = readdirSync('/dev').filter((name) => /^cu\.(usbserial|SLAB_USBtoUART|wchusbserial|usbmodem)/.test(name));
    return ports.length ? `/dev/${ports[0]}` : null;
  } catch { return null; }
}

let intervalS = null;
async function post(reading) {
  try {
    const response = await fetch(`${app}/api/sensors/readings`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...reading, intervalS, source: 'usb-serial' }) });
    console.log(`${new Date().toLocaleTimeString()}  ${reading.nodeId}  soil ${reading.soilPct.toFixed(1)}%  raw ${reading.rawAo ?? '—'}  ${reading.wet ? 'WET' : 'dry'}  → app ${response.ok ? 'ok' : `HTTP ${response.status}`}`);
  } catch (error) {
    console.error(`Could not reach the app at ${app} (${error.message}). Is it running?`);
  }
}

function parse(line) {
  const text = line.trim();
  if (!text) return;
  if (text.startsWith('{')) {
    try { const value = JSON.parse(text); if (value.nodeId && Number.isFinite(Number(value.soilPct))) return void post(value); } catch { /* fall through */ }
  }
  const reading = text.match(/\[Node ([^\]]+)\]\s*raw_AO=(\d+)\s+soil=([\d.]+)%(?:\s+wet=(YES|NO))?(?:\s+DO=\w+\((wet|dry)\))?/i);
  if (reading) {
    return void post({ nodeId: reading[1], rawAo: Number(reading[2]), soilPct: Number(reading[3]), wet: reading[4] ? reading[4].toUpperCase() === 'YES' : undefined, digital: reading[5]?.toLowerCase() });
  }
  const next = text.match(/next in (\d+)s/i);
  if (next) intervalS = Number(next[1]);
  console.log(`  · ${text}`);
}

console.log(`Ultraviolet bridge: ${port} @ ${baud} baud → ${app}/api/sensors/readings`);
// macOS resets serial settings when the port closes, so open the port once and run
// `stty` + `cat` on that same handle (it is the child's stdin).
const fd = openSync(port, 'r');
const child = spawn('/bin/sh', ['-c', `stty ${baud} cs8 -cstopb -parenb raw -echo clocal -hupcl; exec cat`], { stdio: [fd, 'pipe', 'inherit'] });
let buffer = '';
child.stdout.setEncoding('utf8');
child.stdout.on('data', (chunk) => {
  buffer += chunk;
  const lines = buffer.split(/\r?\n/);
  buffer = lines.pop() ?? '';
  lines.forEach(parse);
});
child.on('exit', (code) => { console.error(`Serial reader stopped (code ${code}). Unplugged?`); process.exit(code ?? 1); });
process.on('SIGINT', () => { child.kill(); process.exit(0); });
