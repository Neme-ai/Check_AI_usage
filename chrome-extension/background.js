importScripts('parser.js');
const URLS={codex:'https://chatgpt.com/settings/usage?tab=overview',claude:'https://claude.ai/settings/usage'};
const BASE='http://127.0.0.1:18765';
let ticking=false;
async function settings(){return await chrome.storage.local.get(['token','monitors','lastReload','generation','paused']);}
async function bridge(path,body){
  const {token}=await settings();
  if(!token) throw new Error('请先粘贴悬浮窗配对码');
  const response=await fetch(BASE+path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(4000)});
  if(!response.ok) throw new Error(response.status===403?'配对码不正确':'数据校验未通过');
  return await response.json();
}
async function status(text){await chrome.storage.local.set({connection:text});}
async function snapshot(key,code){await bridge('/usage',{provider:key,status:code,observed_at:Date.now()/1000}).catch(()=>{});}
async function ensureAlarm(){if(!await chrome.alarms.get('usage-tick')) await chrome.alarms.create('usage-tick',{periodInMinutes:.5});}
async function tick(force=false){
  if(ticking) return;
  ticking=true;
  try {
    const config=await settings();
    if(!config.token || config.paused) return;
    let poll;
    try {poll=await bridge('/poll'); await status('已连接本机悬浮窗');}
    catch(error){await status('未连接：请确认悬浮窗已运行及配对码正确');return;}
    const now=Date.now(), last=config.lastReload||{};
    const requested=config.generation!==poll.refresh;
    for(const [key,id] of Object.entries(config.monitors||{})) {
      if(!URLS[key]) continue;
      let tab;
      try {tab=await chrome.tabs.get(id);} catch(_){await snapshot(key,'closed');continue;}
      if(UsageParser.providerForUrl(tab.url)!==key) {await snapshot(key,'wrong_page');continue;}
      if(tab.status==='loading') continue;
      if(force || requested || now-(last[key]||0)>=60000) {
        await chrome.tabs.reload(id);
        last[key]=now;
      }
    }
    await chrome.storage.local.set({lastReload:last,generation:poll.refresh});
  } finally {ticking=false;}
}
async function openMonitor(key){
  if(!URLS[key]) throw new Error('未知平台');
  const config=await settings();
  const monitors=config.monitors||{};
  const old=monitors[key];
  if(old) {
    try {
      const tab=await chrome.tabs.get(old);
      if(UsageParser.providerForUrl(tab.url)===key){await chrome.tabs.update(old,{active:true});await tick(true);return;}
    } catch(_) {}
  }
  // Own a separate pinned usage tab; never reload a user's existing tab.
  const tab=await chrome.tabs.create({url:URLS[key],pinned:true,active:false});
  monitors[key]=tab.id;
  await chrome.storage.local.set({monitors,paused:false});
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  (async()=>{
    if(sender.tab) {
      const config=await settings();
      const key=UsageParser.providerForUrl(sender.url);
      const enabled=!!key && sender.frameId===0 && config.monitors?.[key]===sender.tab.id && !config.paused;
      if(message.type==='IS_MONITOR') return {enabled};
      if(message.type==='SNAPSHOT' && enabled && message.snapshot?.provider===key) {
        const data=message.snapshot;
        if(!['ok','unrecognized'].includes(data.status) || !Array.isArray(data.windows) || data.windows.length>16) throw new Error('无效数据');
        // Explicit allowlist: only quota values and reset text leave Chrome.
        const clean={provider:key,status:data.status,observed_at:data.observed_at,windows:data.windows.map(w=>({key:w.key,used:w.used,reset_at:w.reset_at,reset_text:String(w.reset_text||'').slice(0,160)}))};
        await bridge('/usage',clean);
        await chrome.storage.local.set({['status_'+key]:data.status==='ok'?'已读取 '+new Date().toLocaleTimeString():'页面结构未识别'});
        return {ok:true};
      }
      return {ok:false};
    }
    if(sender.url!==chrome.runtime.getURL('popup.html')) return {ok:false};
    if(message.type==='PAIR') {
      if(!/^[A-Za-z0-9_-]{43}$/.test(message.token||'')) throw new Error('配对码格式不正确');
      await chrome.storage.local.set({token:message.token});
      await bridge('/poll');await status('配对成功');return {ok:true};
    }
    if(message.type==='OPEN') {await openMonitor(message.provider);return {ok:true};}
    if(message.type==='REFRESH') {await tick(true);return {ok:true};}
    if(message.type==='PAUSE') {await chrome.storage.local.set({paused:!!message.paused});return {ok:true};}
    return {ok:false};
  })().then(reply).catch(error=>reply({ok:false,error:error.message}));
  return true;
});
chrome.tabs.onUpdated.addListener((id,change)=>{
  if(change.status==='complete') chrome.tabs.sendMessage(id,{type:'COLLECT'}).catch(()=>{});
});
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='usage-tick') tick().catch(()=>{});});
chrome.runtime.onInstalled.addListener(()=>ensureAlarm());
chrome.runtime.onStartup.addListener(()=>ensureAlarm());
ensureAlarm();
