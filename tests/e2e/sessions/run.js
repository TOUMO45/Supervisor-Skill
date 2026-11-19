#!/usr/bin/env node
'use strict';
// Three-session pilot runner (protocol: tests/e2e/sessions/README.md). One run per call.
//   node tests/e2e/sessions/run.js --arm w|k|e|s --run <n> --out <dir outside both repositories>
//                                  [--eccode <ECCode checkout>]  (arm e only)  [--wall-minutes <per session, default 30>]
//                                  [--variant spread|deferred]  (default spread)   [--memory on|off]  (default on)
// A run is three separate `claude -p` sessions, one after another, in the same workspace. Nothing carries from one
// session to the next except the files in that workspace. The hidden oracle scores the workspace after each session;
// the score after session 3 is the result.
//   w  weak model alone            k  weak model + the autonomous-supervisor skill
//   e  weak model + ECCode         s  strong model alone
// Writes <out>/sessions-<arm>-<n>/{workspace/, s1/, s2/, s3/, result.json}; each sN/ holds transcript.jsonl and
// result.json in the shape ECCode's tools/pilot-trace.js reads.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync, execFileSync } = require('child_process');

const HERE = __dirname;
const SKILL_REPO = path.join(HERE, '..', '..', '..');
const MODELS = { w: 'claude-haiku-5-5', k: 'claude-haiku-5-5', e: 'claude-haiku-5-5', s: 'claude-sonnet-5-5' };
const TOOLS = ['Bash', 'Write', 'Edit', 'MultiEdit', 'Read', 'Glob', 'Grep', 'Task', 'Agent', 'Skill', 'TodoWrite'];
const SESSIONS = ['s1', 's2', 's3'];
const K_PREFIX = 'Use the autonomous-supervisor skill for this work.\n\n';
const WIN = process.platform === 'win32';
const PYTHON = process.env.W1_PYTHON || (WIN ? 'python' : 'python3');
const quote = (a) => (a === '' ? '""' : /[\s"]/.test(a) ? `"${a.replace(/"/g, '\\"')}"` : a);
const slash = (p) => p.split(path.sep).join('/');

function flags(argv) {
  const f = {};
  for (let i = 0; i < argv.length; i += 2) f[argv[i].replace(/^--/, '')] = argv[i + 1];
  return f;
}

function supervisorPlugin(dest) {
  // Only the plugin itself: the tests (and this benchmark's oracle) stay out of the agent's reach.
  if (!fs.existsSync(path.join(dest, 'skills'))) {
    fs.mkdirSync(dest, { recursive: true });
    for (const part of ['.claude-plugin', 'skills']) fs.cpSync(path.join(SKILL_REPO, part), path.join(dest, part), { recursive: true });
  }
  return dest;
}

function eccodePlugin(repo, dest) {
  if (!fs.existsSync(path.join(dest, 'bin', 'eccode.js'))) {
    fs.mkdirSync(dest, { recursive: true });
    const tar = execFileSync('git', ['-C', repo, 'archive', 'HEAD'], { maxBuffer: 1 << 30 });
    execFileSync('tar', ['-x', '-C', dest, '--exclude=docs', '--exclude=.eccode', '--exclude=.supervisor'], { input: tar });
  }
  return dest;
}

function eccodePrompt(repo, pluginDir, ask) {
  // ECCode's own entry command with this session's request in place of $ARGUMENTS (what `/eccode:start <request>` sends).
  const body = fs.readFileSync(path.join(repo, 'commands', 'start.md'), 'utf8').replace(/^---[\s\S]*?---\s*/, '');
  return body.replace('$ARGUMENTS', () => ask).split('${CLAUDE_PLUGIN_ROOT}').join(slash(pluginDir));
}

function score(ws) {
  const r = spawnSync(PYTHON, ['-I', path.join(HERE, 'hidden_acceptance.py'), ws], { encoding: 'utf8', timeout: 600000 });
  const text = r.stdout || '';
  const frac = (re) => { const m = re.exec(text); return m ? { passed: Number(m[1]), total: Number(m[2]) } : null; };
  return {
    oracle: frac(/SCORE (\d+)\/(\d+)/), chat: frac(/CHAT (\d+)\/(\d+)/),
    brief: frac(/in the brief (\d+)\/(\d+)/), s1: frac(/said in session 1 (\d+)\/(\d+)/),
    s2: frac(/said in session 2 (\d+)\/(\d+)/), s3: frac(/said in session 3 (\d+)\/(\d+)/),
    failed: text.split('\n').filter((l) => l.startsWith('FAIL')).map((l) => l.slice(0, 200)),
    oracleTail: (text || r.stderr || '').trim().split('\n').slice(-3),
  };
}

/** Claude Code's own per-project memory files for this workspace (kept under the user profile, outside the folder). */
function harnessMemory(ws) {
  const dir = path.join(os.homedir(), '.claude', 'projects', path.resolve(ws).replace(/[^a-zA-Z0-9]/g, '-'), 'memory');
  try { return fs.readdirSync(dir).filter((n) => n.endsWith('.md')); } catch { return []; }
}

function session(name, arm, model, prompt, extraArgs, ws, dir, wallMs, env) {
  const args = ['-p', '--model', model, '--setting-sources', '', '--strict-mcp-config', '--allowedTools', ...TOOLS,
    '--max-turns', '200', '--output-format', 'stream-json', '--verbose', ...extraArgs];
  const started = Date.now();
  const r = WIN
    ? spawnSync(['claude', ...args.map(quote)].join(' '), { cwd: ws, input: prompt, encoding: 'utf8', timeout: wallMs, maxBuffer: 1 << 30, shell: true, env })
    : spawnSync('claude', args, { cwd: ws, input: prompt, encoding: 'utf8', timeout: wallMs, maxBuffer: 1 << 30, env });
  if (r.error && r.error.code !== 'ETIMEDOUT') throw new Error(`could not start claude: ${r.error.message}`);
  const wall = Math.round((Date.now() - started) / 1000);
  const text = r.stdout || '';
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'transcript.jsonl'), text);
  let last = null; let toolCalls = 0; let assistantMessages = 0; let usedSkill = false; let usedEccode = false;
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    let o; try { o = JSON.parse(line); } catch { continue; }
    if (o.type === 'result') last = o;
    if (o.type === 'assistant') assistantMessages += 1;
    const content = o.message && Array.isArray(o.message.content) ? o.message.content : [];
    for (const b of content) {
      if (b.type !== 'tool_use') continue;
      toolCalls += 1;
      const input = JSON.stringify(b.input || {});
      if ((b.name === 'Skill' && /autonomous-supervisor/.test(input)) || (b.name === 'Bash' && /supervisor\.py/.test(input))) usedSkill = true;
      if ((b.name === 'Bash' && /eccode(\.js)?\b/.test(input)) || (b.name === 'Skill' && /eccode|orchestrate/.test(input))) usedEccode = true;
    }
  }
  const result = {
    project: 'sessions', session: name, arm, model, prompt,
    exit: r.status, timedOut: Boolean(r.error && r.error.code === 'ETIMEDOUT'), wallSeconds: wall, wallLimitMinutes: wallMs / 60000,
    turns: last ? last.num_turns : null, assistantMessages, costUsd: last ? last.total_cost_usd : null, stopReason: last ? last.subtype : null,
    toolCalls, usedSkill: arm === 'k' ? usedSkill : null, usedEccode: arm === 'e' ? usedEccode : null,
    contaminated: /hidden_acceptance|tests[\\/]+e2e/.test(text),
    harnessMemoryFiles: harnessMemory(ws),
    ...score(ws),
    finalMessage: last && typeof last.result === 'string' ? last.result.slice(0, 1500) : null,
  };
  fs.writeFileSync(path.join(dir, 'result.json'), `${JSON.stringify(result, null, 2)}\n`);
  return result;
}

function main() {
  const f = flags(process.argv.slice(2));
  const arm = f.arm;
  if (!MODELS[arm] || !f.run || !f.out) throw new Error('usage: run.js --arm w|k|e|s --run <n> --out <dir> [--eccode <ECCode checkout>] [--wall-minutes <n>]');
  const out = path.resolve(f.out);
  for (const repo of [SKILL_REPO, f.eccode].filter(Boolean)) {
    const rel = path.relative(path.resolve(repo), out);
    if (!rel.startsWith('..') && !path.isAbsolute(rel)) throw new Error(`--out must be outside ${path.resolve(repo)}: the agent must not be able to find the oracle`);
  }
  // --variant deferred: every chat-only requirement is said in session 1, including those for parts built later.
  const variant = f.variant || 'spread';
  if (!['spread', 'deferred'].includes(variant)) throw new Error('--variant spread|deferred');
  const promptDir = variant === 'deferred' ? 'prompts-deferred' : 'prompts';
  // --memory off: Claude Code's own cross-session memory is disabled, so only the folder carries over.
  const memoryOff = f.memory === 'off';
  if (f.memory && !['on', 'off'].includes(f.memory)) throw new Error('--memory on|off');
  const env = memoryOff ? { ...process.env, CLAUDE_CODE_DISABLE_AUTO_MEMORY: '1' } : process.env;
  const tag = `${variant === 'deferred' ? 'deferred-' : ''}${memoryOff ? 'nomem-' : ''}`;
  const dir = path.join(out, `sessions-${tag}${arm}-${f.run}`);
  if (fs.existsSync(dir)) throw new Error(`${dir} exists: a run is done once`);
  const ws = path.join(dir, 'workspace');
  fs.mkdirSync(ws, { recursive: true });
  fs.copyFileSync(path.join(HERE, 'brief.md'), path.join(ws, 'brief.md'));
  const extra = [];
  let wrap = (ask) => ask;
  if (arm === 'k') {
    extra.push('--plugin-dir', supervisorPlugin(path.join(out, 'supervisor-plugin')));
    wrap = (ask) => K_PREFIX + ask;
  }
  if (arm === 'e') {
    if (!f.eccode) throw new Error('arm e needs --eccode <ECCode checkout>');
    const repo = path.resolve(f.eccode);
    const pluginDir = eccodePlugin(repo, path.join(out, 'eccode-plugin'));
    extra.push('--plugin-dir', pluginDir);
    wrap = (ask) => eccodePrompt(repo, pluginDir, ask);
  }
  const wallMs = (f['wall-minutes'] ? Number(f['wall-minutes']) : 30) * 60 * 1000;
  const results = [];
  for (const name of SESSIONS) {
    const ask = fs.readFileSync(path.join(HERE, promptDir, `${name}.md`), 'utf8').trim();
    const r = session(name, arm, MODELS[arm], wrap(ask), extra, ws, path.join(dir, name), wallMs, env);
    results.push(r);
    const c = r.chat ? `${r.chat.passed}/${r.chat.total}` : 'n/a';
    const q = r.oracle ? `${r.oracle.passed}/${r.oracle.total}` : 'n/a';
    process.stdout.write(`  ${name}: after it Q ${q} chat ${c}  cost ${r.costUsd === null ? 'n/a' : r.costUsd.toFixed(2)}  ${r.turns} turns  ${r.wallSeconds}s${r.timedOut ? '  TIMED OUT' : ''}\n`);
  }
  const end = results[results.length - 1];
  const sum = (k) => results.reduce((a, r) => a + (r[k] || 0), 0);
  const priced = results.every((r) => r.costUsd !== null);
  const final = {
    project: 'sessions', variant, harnessMemory: memoryOff ? 'off' : 'on', harnessMemoryFiles: end.harnessMemoryFiles, arm, run: Number(f.run), model: MODELS[arm],
    oracle: end.oracle, chat: end.chat, byOrigin: { brief: end.brief, s1: end.s1, s2: end.s2, s3: end.s3 }, failed: end.failed,
    costUsd: priced ? sum('costUsd') : null, wallSeconds: sum('wallSeconds'), turns: sum('turns'),
    anyTimedOut: results.some((r) => r.timedOut), contaminated: results.some((r) => r.contaminated),
    usedSkill: arm === 'k' ? results.map((r) => r.usedSkill) : null, usedEccode: arm === 'e' ? results.map((r) => r.usedEccode) : null,
    sessions: results.map((r) => ({ session: r.session, oracle: r.oracle, chat: r.chat, costUsd: r.costUsd, turns: r.turns, wallSeconds: r.wallSeconds, timedOut: r.timedOut, stopReason: r.stopReason })),
  };
  fs.writeFileSync(path.join(dir, 'result.json'), `${JSON.stringify(final, null, 2)}\n`);
  const o = (x) => (x ? `${x.passed}/${x.total}` : 'n/a');
  const used = arm === 'k' ? `  skill:${final.usedSkill.map((u) => (u ? 'y' : 'n')).join('')}` : arm === 'e' ? `  eccode:${final.usedEccode.map((u) => (u ? 'y' : 'n')).join('')}` : '';
  process.stdout.write(`sessions${tag ? `-${tag.slice(0, -1)}` : ''} ${arm}${f.run}: Q ${o(final.oracle)}  CHAT ${o(final.chat)}  (s1 ${o(end.s1)} s2 ${o(end.s2)} s3 ${o(end.s3)} brief ${o(end.brief)})  cost ${priced ? final.costUsd.toFixed(2) : 'n/a'}  ${final.turns} turns  ${final.wallSeconds}s${used}  contaminated:${final.contaminated}  harness-memory-files:${end.harnessMemoryFiles.length}\n`);
}

try { main(); } catch (e) { process.stderr.write(`${e.message}\n`); process.exitCode = 1; }
