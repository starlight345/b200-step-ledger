#!/usr/bin/env node

/*
 * Rebuild the Korean Scenario Lab walkthrough from the current static pages.
 *
 * Requirements:
 *   NODE_PATH=<directory containing playwright>
 *   FFMPEG_BIN=<full ffmpeg binary>
 *
 * The script uses the macOS Yuna voice by default and writes only the final
 * MP4, VTT, poster, and a JSON build report into assets/.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const ASSETS = path.join(ROOT, 'assets');
const NARRATION = path.join(ASSETS, 'b200_walkthrough_narration_v2.ko.txt');
const OUT_VIDEO = path.join(ASSETS, 'b200_walkthrough_v2.mp4');
const OUT_VTT = path.join(ASSETS, 'b200_walkthrough_v2.ko.vtt');
const OUT_POSTER = path.join(ASSETS, 'b200_walkthrough_v2_poster.png');
const OUT_REPORT = path.join(ASSETS, 'b200_walkthrough_v2.build.json');
const FFMPEG = process.env.FFMPEG_BIN;
const CHROME = process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const VOICE = process.env.WALKTHROUGH_VOICE || 'Yuna';
const VOICE_RATE = process.env.WALKTHROUGH_RATE || '178';
const PORT = Number(process.env.WALKTHROUGH_PORT || 4174);
const BASE = `http://127.0.0.1:${PORT}`;
const VIEWPORT = { width: 1280, height: 720 };
const GAP_SECONDS = 0.35;

if (!FFMPEG || !fs.existsSync(FFMPEG)) {
  throw new Error('Set FFMPEG_BIN to a full ffmpeg binary with libx264 support.');
}
if (!fs.existsSync(CHROME)) throw new Error(`Chrome not found: ${CHROME}`);

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: 'inherit', ...options });
  if (result.status !== 0) throw new Error(`${command} failed with status ${result.status}`);
}

function probeDuration(file) {
  const result = spawnSync(FFMPEG, ['-hide_banner', '-i', file], { encoding: 'utf8' });
  const text = `${result.stdout || ''}\n${result.stderr || ''}`;
  const match = text.match(/Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)/);
  if (!match) throw new Error(`Could not read duration: ${file}`);
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
}

function parseScenes(source) {
  const parts = source.trim().split(/^\[(\d{2}) · ([^\]]+)\]\s*$/m);
  const scenes = [];
  for (let i = 1; i < parts.length; i += 3) {
    scenes.push({ number: parts[i], title: parts[i + 1], text: parts[i + 2].trim() });
  }
  if (scenes.length !== 8) throw new Error(`Expected 8 narration scenes, found ${scenes.length}`);
  return scenes;
}

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function click(page, selector) {
  const target = page.locator(selector).first();
  await target.scrollIntoViewIfNeeded();
  await target.click();
}

async function select(page, selector, value) {
  const target = page.locator(selector).first();
  await target.scrollIntoViewIfNeeded();
  await target.selectOption(value);
}

async function smoothScroll(page, target, offset = -24) {
  await page.locator(target).first().evaluate((node, y) => {
    window.scrollTo({ top: node.getBoundingClientRect().top + window.scrollY + y, behavior: 'smooth' });
  }, offset);
}

async function paced(durationSeconds, actions) {
  const sceneMs = Math.max(1000, durationSeconds * 1000);
  const slot = sceneMs / Math.max(1, actions.length);
  for (const action of actions) {
    const started = Date.now();
    await action();
    await wait(Math.max(150, slot - (Date.now() - started)));
  }
}

function secondsToVtt(value) {
  const ms = Math.max(0, Math.round(value * 1000));
  const hours = Math.floor(ms / 3600000);
  const minutes = Math.floor((ms % 3600000) / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  const millis = ms % 1000;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`;
}

function captionChunks(text) {
  const sentences = text.replace(/\n+/g, ' ').match(/[^.!?。]+[.!?。]?/g) || [text];
  const chunks = [];
  let current = '';
  for (const sentence of sentences.map(item => item.trim()).filter(Boolean)) {
    if (current && current.length + sentence.length > 62) {
      chunks.push(current);
      current = sentence;
    } else {
      current = current ? `${current} ${sentence}` : sentence;
    }
  }
  if (current) chunks.push(current);
  return chunks;
}

function makeVtt(scenes) {
  const lines = ['WEBVTT', '', 'NOTE Ledger3D Scenario Lab walkthrough v2 · Korean narration', ''];
  let cursor = 0;
  let cue = 1;
  for (const scene of scenes) {
    const chunks = captionChunks(scene.text);
    const totalWeight = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const speechDuration = Math.max(0.5, scene.duration - GAP_SECONDS);
    let local = cursor;
    for (const chunk of chunks) {
      const chunkDuration = speechDuration * chunk.length / totalWeight;
      const end = local + chunkDuration;
      lines.push(String(cue++), `${secondsToVtt(local)} --> ${secondsToVtt(end)}`, chunk, '');
      local = end;
    }
    cursor += scene.duration;
  }
  fs.writeFileSync(OUT_VTT, `${lines.join('\n')}\n`);
}

async function record(scenes, tempDir) {
  const browser = await chromium.launch({ headless: true, executablePath: CHROME, args: ['--hide-scrollbars'] });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
    colorScheme: 'dark',
    recordVideo: { dir: tempDir, size: VIEWPORT },
  });
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));

  await page.goto(`${BASE}/scenario-lab.html`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: OUT_POSTER });

  await paced(scenes[0].duration, [
    () => page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })),
    () => smoothScroll(page, '.presets', -120),
    () => smoothScroll(page, '#stage', -25),
  ]);

  await paced(scenes[1].duration, [
    () => click(page, '[data-s="short"]'),
    () => smoothScroll(page, '#stage', -20),
    () => smoothScroll(page, '.storage-overview', -20),
    () => click(page, '[data-s="long"]'),
    () => smoothScroll(page, '.metrics', -20),
    () => smoothScroll(page, '.pressure', -30),
  ]);

  await paced(scenes[2].duration, [
    () => smoothScroll(page, '.presets', -100),
    () => click(page, '[data-s="state"]'),
    () => click(page, '[data-s="sliding"]'),
    () => click(page, '[data-s="moe"]'),
    () => click(page, '[data-s="mla"]'),
    () => smoothScroll(page, '#stage', -20),
  ]);

  await paced(scenes[3].duration, [
    () => smoothScroll(page, '.presets', -100),
    () => click(page, '[data-s="cliff"]'),
    () => smoothScroll(page, '.metrics', -20),
    () => smoothScroll(page, '#limit', -60),
    () => page.goto(`${BASE}/memory.html#placement-proof`, { waitUntil: 'networkidle' }),
    () => smoothScroll(page, '#placement-proof', -10),
    () => smoothScroll(page, '#placement-proof .table-wrap', -30),
  ]);

  await paced(scenes[4].duration, [
    () => page.goto(`${BASE}/scenario-lab.html`, { waitUntil: 'networkidle' }),
    () => click(page, '#view-journey'),
    () => select(page, '#journey-pattern', 'cold'),
    () => click(page, '#reset-journey'),
    () => click(page, '#play'),
    () => select(page, '#journey-pattern', 'reuse'),
    () => click(page, '#play'),
    () => select(page, '#journey-pattern', 'eviction'),
    () => click(page, '#play'),
    () => select(page, '#journey-pattern', 'dirty'),
    () => click(page, '#play'),
    () => smoothScroll(page, '.assumptions', -40),
  ]);

  await paced(scenes[5].duration, [
    () => page.goto(`${BASE}/memory.html#placement-proof`, { waitUntil: 'networkidle' }),
    () => smoothScroll(page, '#placement-proof', -10),
    () => smoothScroll(page, '#placement-proof .concepts', -20),
    () => smoothScroll(page, '#placement-proof .plot', -30),
    () => smoothScroll(page, '#placement-proof .table-wrap', -30),
    () => smoothScroll(page, '#policy', -20),
  ]);

  await paced(scenes[6].duration, [
    () => page.goto(`${BASE}/replay.html?autoplay=1`, { waitUntil: 'networkidle' }),
    () => smoothScroll(page, '#replaybar', -10),
    () => click(page, '#replay-toggle'),
    () => smoothScroll(page, '#request-life', -30),
    () => smoothScroll(page, '#scene-wrap', -30),
    () => smoothScroll(page, '#chart', -30),
    () => smoothScroll(page, '#pipeline-explainer', -30),
  ]);

  await paced(scenes[7].duration, [
    () => page.goto(`${BASE}/scenario-lab.html`, { waitUntil: 'networkidle' }),
    () => smoothScroll(page, '.evidence', -30),
    () => page.goto(`${BASE}/memory.html#return`, { waitUntil: 'networkidle' }),
    () => smoothScroll(page, '#return', -20),
    () => smoothScroll(page, '#sources', -20),
    () => page.goto(`${BASE}/scenario-lab.html`, { waitUntil: 'networkidle' }),
    () => smoothScroll(page, '.evidence', -30),
  ]);

  await wait(1200);
  const video = page.video();
  await context.close();
  const videoPath = await video.path();
  await browser.close();
  if (pageErrors.length) throw new Error(`Browser page errors:\n${pageErrors.join('\n')}`);
  return videoPath;
}

async function main() {
  const scenes = parseScenes(fs.readFileSync(NARRATION, 'utf8'));
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ledger3d-walkthrough-v2-'));
  const audioFiles = [];

  for (const scene of scenes) {
    const textPath = path.join(tempDir, `scene-${scene.number}.txt`);
    const audioPath = path.join(tempDir, `scene-${scene.number}.aiff`);
    fs.writeFileSync(textPath, scene.text);
    run('/usr/bin/say', ['-v', VOICE, '-r', VOICE_RATE, '-f', textPath, '-o', audioPath]);
    scene.duration = probeDuration(audioPath) + GAP_SECONDS;
    audioFiles.push(audioPath);
  }

  const audioList = path.join(tempDir, 'audio-concat.txt');
  fs.writeFileSync(audioList, `${audioFiles.map(file => `file '${file.replaceAll("'", "'\\''")}'`).join('\n')}\n`);
  const combinedAudio = path.join(tempDir, 'narration.wav');
  run(FFMPEG, ['-y', '-hide_banner', '-loglevel', 'warning', '-f', 'concat', '-safe', '0', '-i', audioList, '-c:a', 'pcm_s16le', combinedAudio]);
  makeVtt(scenes);

  const server = spawn('/usr/bin/python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1'], {
    cwd: ROOT,
    stdio: 'ignore',
  });
  try {
    await wait(800);
    const rawVideo = await record(scenes, tempDir);
    run(FFMPEG, [
      '-y', '-hide_banner', '-loglevel', 'warning',
      '-i', rawVideo, '-i', combinedAudio,
      '-c:v', 'libx264', '-preset', 'medium', '-crf', '22', '-pix_fmt', 'yuv420p',
      '-c:a', 'aac', '-b:a', '128k', '-ar', '48000',
      '-movflags', '+faststart', '-shortest', OUT_VIDEO,
    ]);
  } finally {
    server.kill('SIGTERM');
  }

  const report = {
    generatedAt: new Date().toISOString(),
    source: 'scenario-lab.html, memory.html, replay.html',
    narration: path.relative(ROOT, NARRATION),
    voice: VOICE,
    voiceRate: Number(VOICE_RATE),
    viewport: VIEWPORT,
    durationSeconds: probeDuration(OUT_VIDEO),
    scenes: scenes.map(scene => ({
      number: scene.number,
      title: scene.title,
      durationSeconds: Number(scene.duration.toFixed(2)),
    })),
  };
  fs.writeFileSync(OUT_REPORT, `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
