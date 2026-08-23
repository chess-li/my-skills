#!/usr/bin/env node
// prototype-anchor — 原型锚点 HTTP 服务：data-term-anchor 写盘与术语表同步，全项目共用。
//
// 用法：prototype-anchor serve [端口]   （默认 8420）
//
// 生命周期：启动幂等——先探活 127.0.0.1:端口/__am_ping，已存活则直接退出 0；
// 端口被非本服务占用则报错退出 1。无请求超过 AM_IDLE_MIN 分钟（默认 2）
// 自动退出——服务无状态（状态全在磁盘），消亡无损失，需要时重新启动即可。
//
// 写盘面：POST /__am_save 按 DOM 路径（html:0/body:0/div:1，同标签兄弟序号）
// 在源码对应起始标签精确插入/替换 data-term-anchor，并把新术语同步进项目内
// 唯一引用锚点的术语表。安全面：仅写白名单根目录（默认 ~/workspace，
// AM_ALLOW 冒号分隔追加）内的 .html；术语表写入仅限项目 docs/contexts 下。
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const VERSION = '0.3.0';
const ALLOW = [path.join(os.homedir(), 'workspace'),
  ...(process.env.AM_ALLOW ? process.env.AM_ALLOW.split(':') : [])]
  .map(p => path.resolve(p));
const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
  'link', 'meta', 'param', 'source', 'track', 'wbr']);

function allowed(f) {
  const r = path.resolve(f);
  return ALLOW.some(a => r === a || r.startsWith(a + path.sep));
}

// 与客户端 amPath 同构的源码元素树：节点记录起始标签的绝对区间 [start, end)
function parseTree(text) {
  const root = { tag: '', children: [] };
  const stack = [root];
  let i = 0;
  while (i < text.length) {
    const lt = text.indexOf('<', i);
    if (lt < 0) break;
    if (text.startsWith('<!--', lt)) {
      const e = text.indexOf('-->', lt + 4);
      i = e < 0 ? text.length : e + 3; continue;
    }
    if (text.startsWith('<!', lt) || text.startsWith('<?', lt)) {
      const e = text.indexOf('>', lt + 2);
      i = e < 0 ? text.length : e + 1; continue;
    }
    if (text.startsWith('</', lt)) {
      const m = /^<\/\s*([a-zA-Z0-9-]+)/.exec(text.slice(lt, lt + 64));
      const e = text.indexOf('>', lt + 2);
      i = e < 0 ? text.length : e + 1;
      if (m) {
        const t = m[1].toLowerCase();
        for (let s = stack.length - 1; s > 0; s--)
          if (stack[s].tag === t) { stack.length = s; break; }
      }
      continue;
    }
    const m = /^<\s*([a-zA-Z][a-zA-Z0-9-]*)/.exec(text.slice(lt, lt + 64));
    if (!m) { i = lt + 1; continue; }
    const tag = m[1].toLowerCase();
    let j = lt + m[0].length, q = null;
    while (j < text.length) {
      const c = text[j];
      if (q) { if (c === q) q = null; }
      else if (c === '"' || c === "'") q = c;
      else if (c === '>') break;
      j++;
    }
    if (j >= text.length) break;
    const node = { tag, children: [], start: lt, end: j + 1 };
    stack[stack.length - 1].children.push(node);
    if (text[j - 1] !== '/' && !VOID.has(tag)) stack.push(node);
    i = j + 1;
  }
  return root;
}

function findByPath(root, domPath) {
  let node = root;
  for (const seg of domPath.split('/')) {
    const k = seg.lastIndexOf(':');
    const tag = seg.slice(0, k), idx = +seg.slice(k + 1);
    const same = node.children.filter(c => c.tag === tag);
    if (!(idx >= 0 && idx < same.length)) throw new Error('path not found: ' + domPath);
    node = same[idx];
  }
  return node;
}

// 从原型文件向上找含 docs/contexts 的项目根
function projectRootOf(file) {
  let d = path.dirname(path.resolve(file));
  while (true) {
    if (fs.existsSync(path.join(d, 'docs', 'contexts'))) return d;
    const p = path.dirname(d);
    if (p === d) return null;
    d = p;
  }
}

function syncDomains(file, term, anchor, def, attr) {
  attr = attr || 'data-term-anchor';
  if (!term) return null;
  const root = projectRootOf(file);
  if (!root) return null;
  const ctx = path.join(root, 'docs', 'contexts');
  const files = [];
  for (const bc of fs.readdirSync(ctx)) {
    const dir = path.join(ctx, bc);
    try {
      for (const n of fs.readdirSync(dir))
        if (n.endsWith('-domains.md')) files.push(path.join(dir, n));
    } catch { /* 非目录跳过 */ }
  }
  const hit = files.filter(f =>
    fs.readFileSync(f, 'utf8').includes('data-term-anchor'));
  if (hit.length !== 1) return null;
  const f = hit[0];
  const text = fs.readFileSync(f, 'utf8');
  if (text.includes(`${attr}="${anchor}"`)) return '术语表已存在';
  const lines = text.split('\n');
  let lastRow = -1;
  lines.forEach((l, i) => { if (l.startsWith('| **')) lastRow = i; });
  if (lastRow < 0) return null;
  const label = attr === 'data-anchor-member' ? '原型组锚点' : '原型锚点';
  lines.splice(lastRow + 1, 0,
    `| **${term}** | ${def || '（待补定义）'}，${label} \`[${attr}="${anchor}"]\` | — |`);
  const today = new Date().toISOString().slice(0, 10);
  while (lines.length && lines[lines.length - 1] === '') lines.pop();
  lines.push(`- ${today} 锚点视图模式新增${attr === 'data-anchor-member' ? '分组' : ''}：${term}（${anchor}）`);
  fs.writeFileSync(f, lines.join('\n') + '\n', 'utf8');
  return '术语表已同步';
}

function saveAnchor(b) {
  const file = String(b.file || '');
  if (!file.endsWith('.html') || !path.isAbsolute(file) || !allowed(file))
    return { error: 'file rejected' };
  if (!fs.existsSync(file)) return { error: 'file not found' };
  const attr = b.attr === 'data-anchor-member' ? 'data-anchor-member' : 'data-term-anchor';
  const anchor = String(b.anchor || '');
  if (!/^[a-z0-9][a-z0-9-]*$/.test(anchor))
    return { error: 'anchor 值须为 kebab-case' };
  const text = fs.readFileSync(file, 'utf8');
  const paths = Array.isArray(b.paths) && b.paths.length ? b.paths.map(String) : [String(b.path || '')];
  const root = parseTree(text);
  const nodes = [];
  for (const p of paths) {
    try { nodes.push(findByPath(root, p)); }
    catch (e) { return { error: e.message }; }
  }
  // 起始标签区间互不相交：按 start 降序改写，先改后面的，前面的偏移不失效
  nodes.sort((x, y) => y.start - x.start);
  const re = new RegExp('\\s' + attr + '="[^"]*"');
  let out = text;
  for (const node of nodes) {
    const tagText = out.slice(node.start, node.end);
    const m = re.exec(tagText);
    let newTag;
    if (m) {
      newTag = tagText.slice(0, m.index) + ` ${attr}="${anchor}"` + tagText.slice(m.index + m[0].length);
    } else {
      let ins = tagText.length - 1;
      if (tagText[ins - 1] === '/') ins--;
      newTag = tagText.slice(0, ins) + ` ${attr}="${anchor}"` + tagText.slice(ins);
    }
    out = out.slice(0, node.start) + newTag + out.slice(node.end);
  }
  fs.writeFileSync(file, out, 'utf8');
  return { ok: true, count: nodes.length, domains: syncDomains(file, b.term, anchor, b.def || '', attr) };
}

function cors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
}

function send(res, code, obj) {
  const data = Buffer.from(JSON.stringify(obj));
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(data);
}

function serve(port) {
  // 幂等启动：先探活，本服务已存活则直接退出 0
  const probe = http.get({ host: '127.0.0.1', port, path: '/__am_ping', timeout: 1500 }, res => {
    res.resume();
    if (res.statusCode === 200) {
      console.error(`prototype-anchor 已在运行（127.0.0.1:${port}），无需重复启动`);
      process.exit(0);
    }
    bind();
  });
  probe.on('error', bind);          // 连接被拒 → 无服务 → 正常启动
  probe.on('timeout', () => { probe.destroy(); bind(); });

  function bind() {
    const idleMs = +(process.env.AM_IDLE_MIN || 2) * 60 * 1000;
    let lastSeen = Date.now();
    const server = http.createServer((req, res) => {
      lastSeen = Date.now();
      cors(res);
      if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
      const u = new URL(req.url, 'http://x');
      if (req.method === 'GET' && u.pathname === '/__am_ping')
        return send(res, 200, { ok: true, version: VERSION });
      if (req.method === 'POST' && u.pathname === '/__am_shutdown') {
        send(res, 200, { ok: true, bye: true });
        setImmediate(() => process.exit(0));
        return;
      }
      if (req.method === 'POST' && u.pathname === '/__am_save') {
        let raw = '';
        req.on('data', c => { raw += c; });
        req.on('end', () => {
          let b; try { b = JSON.parse(raw || '{}'); } catch { return send(res, 400, { error: 'bad json' }); }
          const r = saveAnchor(b);
          send(res, r.ok ? 200 : 422, r);
        });
        return;
      }
      if (req.method === 'GET' && u.pathname === '/proto') {
        const abs = u.searchParams.get('abs') || '';
        if (abs.endsWith('.html') && path.isAbsolute(abs) && allowed(abs) && fs.existsSync(abs)) {
          res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
          res.end(fs.readFileSync(abs));
        } else send(res, 403, { error: 'rejected' });
        return;
      }
      send(res, 404, { error: 'not found' });
    });
    server.on('error', e => {
      if (e.code === 'EADDRINUSE') {
        console.error(`端口 ${port} 被其他服务占用（非 prototype-anchor），未启动`);
        process.exit(1);
      }
      throw e;
    });
    setInterval(() => {
      if (Date.now() - lastSeen > idleMs) {
        console.error(`空闲 ${idleMs / 60000} 分钟无请求，自动退出`);
        process.exit(0);
      }
    }, Math.min(idleMs, 30000)).unref();
    server.listen(port, '127.0.0.1', () =>
      console.error(`prototype-anchor http://127.0.0.1:${port}  allow: ${ALLOW.join(', ')}  idle-exit: ${idleMs / 60000}min`));
  }
}

if (process.argv[2] === 'serve') serve(+(process.argv[3] || 8420));
else {
  console.error('用法：prototype-anchor serve [端口]（默认 8420；幂等启动，空闲自动退出）');
  process.exit(1);
}
