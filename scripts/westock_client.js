#!/usr/bin/env node
/**
 * westock_client.js — 直接调用本机 WorkBuddy 已授权的「腾讯自选股」MCP。
 *
 * 用途：当 agent 所在环境没有把 data_* 工具挂上来（例如在 DSH / 终端里跑），
 *      但本机 WorkBuddy 已经连接过腾讯自选股时，用这个脚本取数。
 *
 * 依赖：Node ≥ 18（用内置 crypto + fetch），零第三方包。
 * 安全：只读取本机已授权的凭据，不做任何绕过；token 只在内存里，不打印、不落盘。
 *
 * 用法：
 *   node westock_client.js check
 *   node westock_client.js tools
 *   node westock_client.js call data_quote '{"code":"sz301101"}'
 *   node westock_client.js call data_finance '{"code":"sz301101","fields":"all","num":16}' > /tmp/fin.json
 *
 * 环境变量：
 *   WORKBUDDY_HOME   自定义 ~/.workbuddy 位置
 *   WESTOCK_INTERVAL 每次调用之间的间隔毫秒（默认 1600，防「服务限频」）
 */

'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');

const WB_HOME = process.env.WORKBUDDY_HOME || path.join(os.homedir(), '.workbuddy');
const HKDF_INFO = Buffer.from('workbuddy-oauth-credentials-v1', 'utf8');
const INTERVAL = Number(process.env.WESTOCK_INTERVAL || 1600);

function die(msg) {
  console.error(`[westock] ${msg}`);
  process.exit(1);
}

/** 1. 从连接器插件缓存里读 MCP 端点 */
function findEndpoint() {
  const base = path.join(WB_HOME, 'plugins', 'cache', 'workbuddy-connector-plugins-official', 'westock-mcp');
  if (!fs.existsSync(base)) {
    die(`没找到 westock-mcp 插件：${base}\n  说明本机没装过腾讯自选股连接器，或者 WorkBuddy 版本路径不同。`);
  }
  const versions = fs.readdirSync(base).filter((d) => fs.existsSync(path.join(base, d, 'mcp.json')));
  if (!versions.length) die(`${base} 下没有 mcp.json`);
  const cfg = JSON.parse(fs.readFileSync(path.join(base, versions.sort().pop(), 'mcp.json'), 'utf8'));
  const srv = (cfg.mcpServers || {})['westock-mcp'];
  if (!srv || !srv.url) die('mcp.json 里没有 westock-mcp 的 url');
  return { url: srv.url, type: srv.type || 'streamable-http' };
}

/** 2. 找到已授权的账号目录（含 .credentials.v3.json 与 .master.key 的那个） */
function findAccount() {
  const root = path.join(WB_HOME, 'connectors');
  if (!fs.existsSync(root)) die(`没有 ${root}`);
  for (const id of fs.readdirSync(root)) {
    const dir = path.join(root, id);
    const cred = path.join(dir, '.credentials.v3.json');
    const key = path.join(dir, '.master.key');
    if (!fs.existsSync(cred) || !fs.existsSync(key)) continue;
    const j = JSON.parse(fs.readFileSync(cred, 'utf8'));
    const serverKey = Object.keys(j.mcpOAuth || {}).find((k) => k.startsWith('westock-mcp'));
    if (serverKey) return { accountId: id, dir, cred: j, masterKey: fs.readFileSync(key), serverKey };
  }
  die('没有找到已授权的 westock-mcp 凭据。\n' +
      '  先在 WorkBuddy 的「连接器」里完成一次腾讯自选股授权（OAuth 必须人工点一次），再回来跑。');
}

/**
 * 3. 解密 access token
 *    scheme : aes-256-gcm
 *    key    : HKDF-SHA256(ikm = masterKey ‖ userId, salt = 信封里的 salt, info = HKDF_INFO)
 *    aad    : `${userId}|${serverKey}|${fieldName}`
 *    userId : 账号目录名（实测就是 connectors/ 下的目录名本身）
 */
function decrypt(userId, serverKey, fieldName, envelope, masterKey, saltB64) {
  const salt = Buffer.from(saltB64, 'base64');
  const ikm = Buffer.concat([masterKey, Buffer.from(userId, 'utf8')]);
  const key = Buffer.from(crypto.hkdfSync('sha256', ikm, salt, HKDF_INFO, 32));
  const d = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(envelope.iv, 'base64'));
  d.setAAD(Buffer.from(`${userId}|${serverKey}|${fieldName}`, 'utf8'));
  d.setAuthTag(Buffer.from(envelope.tag, 'base64'));
  return Buffer.concat([d.update(Buffer.from(envelope.ct, 'base64')), d.final()]).toString('utf8');
}

function getToken() {
  const acc = findAccount();
  const env = acc.cred.mcpOAuth[acc.serverKey];
  const salt = acc.cred.encryption && acc.cred.encryption.salt;
  if (!salt) die('凭据文件里没有 encryption.salt');
  let token;
  try {
    token = decrypt(acc.accountId, acc.serverKey, 'accessToken', env.accessToken, acc.masterKey, salt);
  } catch (e) {
    // 账号 id 可能带后缀，退一步试完整 accountIdentityKey
    const alt = acc.cred.accountIdentityKey;
    if (!alt) die(`解密失败：${e.message}\n  账号 id 可能不是目录名，且没有 accountIdentityKey 可退。`);
    token = decrypt(alt, acc.serverKey, 'accessToken', env.accessToken, acc.masterKey, salt);
  }
  return { token, expiresAt: env.expiresAt, serverKey: acc.serverKey, accountId: acc.accountId };
}

/* ---------- MCP over streamable-http ---------- */
let SESSION = '';

async function rpc(url, token, payload) {
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream',
  };
  if (SESSION) headers['Mcp-Session-Id'] = SESSION;

  const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(payload) });
  const sid = res.headers.get('mcp-session-id');
  if (sid) SESSION = sid;

  const raw = await res.text();          // 可能是 SSE，也可能是空体（通知）
  if (!res.ok && !raw.trim()) die(`HTTP ${res.status}`);
  if (!raw.trim()) return null;

  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith('data: ')) return JSON.parse(line.slice(6));
  }
  try {
    return JSON.parse(raw);
  } catch {
    // 限频等错误会以纯文本返回，这里必须显式报出来，否则会被当成「没有数据」
    die(`返回不是 JSON（很可能是限频或鉴权失败）：\n  ${raw.slice(0, 300)}`);
  }
}

async function open(url, token) {
  await rpc(url, token, {
    jsonrpc: '2.0', id: 1, method: 'initialize',
    params: { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'westock_client', version: '1.0' } },
  });
  await rpc(url, token, { jsonrpc: '2.0', method: 'notifications/initialized' });
}

function toolText(resp) {
  if (!resp) return '';
  if (resp.error) return `[MCP error] ${JSON.stringify(resp.error)}`;
  const content = (resp.result && resp.result.content) || [];
  return content.map((c) => c.text || '').join('');
}

(async () => {
  const cmd = process.argv[2] || 'check';
  const { url } = findEndpoint();
  const t = getToken();
  const expired = t.expiresAt && t.expiresAt < Date.now();

  if (cmd === 'check') {
    console.log(`端点    ${url}`);
    console.log(`账号    ${t.accountId}`);
    console.log(`授权    ${t.serverKey}`);
    console.log(`有效期  ${t.expiresAt ? new Date(t.expiresAt).toISOString() : '未知'}${expired ? '  ← 已过期，需回 WorkBuddy 重新授权' : ''}`);
    if (expired) process.exit(2);
    await open(url, t.token);
    console.log('连通    是（initialize 成功）');
    return;
  }

  if (expired) die('access token 已过期：回 WorkBuddy 的连接器里重新授权一次（会自动续期）。');

  await open(url, t.token);

  if (cmd === 'tools') {
    const r = await rpc(url, t.token, { jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} });
    for (const tool of (r.result && r.result.tools) || []) {
      console.log(`${tool.name}\t${(tool.description || '').split('\n')[0].slice(0, 80)}`);
    }
    return;
  }

  if (cmd === 'call') {
    const name = process.argv[3];
    if (!name) die('用法：call <tool> \'<json args>\'');
    let args = {};
    if (process.argv[4]) {
      try { args = JSON.parse(process.argv[4]); } catch (e) { die(`参数不是合法 JSON：${e.message}`); }
    }
    await new Promise((r) => setTimeout(r, INTERVAL));   // 防限频
    const r = await rpc(url, t.token, {
      jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name, arguments: args },
    });
    const text = toolText(r);
    try {
      console.log(JSON.stringify(JSON.parse(text), null, 2));   // 美化
    } catch {
      console.log(text);
    }
    return;
  }

  die(`未知命令 ${cmd}；可用：check / tools / call`);
})();
