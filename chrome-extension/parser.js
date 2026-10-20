/* Reads only labelled quota meters, never credit balances or product mix. */
(function(root) {
  const providerForUrl = value => {
    try {
      const u = new URL(value);
      if (u.protocol !== 'https:') return null;
      if (u.hostname === 'chatgpt.com' && ['/settings/usage','/codex/settings/usage'].includes(u.pathname.replace(/\/$/,''))) return 'codex';
      if (u.hostname === 'claude.ai' && (u.pathname.replace(/\/$/,'') === '/settings/usage' || (u.pathname === '/new' && u.hash === '#settings/usage'))) return 'claude';
    } catch (_) {}
    return null;
  };
  function absoluteReset(text) {
    const m = String(text).match(/(\d{4})年(\d{1,2})月(\d{1,2})日.*?GMT([+-])(\d{1,2})(?::(\d{2}))?\s+(\d{1,2}):(\d{2}):(\d{2})/);
    if (m) {
      const offset = (Number(m[5])*60 + Number(m[6] || 0)) * (m[4] === '+' ? 1 : -1);
      return Date.UTC(+m[1],+m[2]-1,+m[3],+m[7],+m[8],+m[9])/1000 - offset*60;
    }
    // Only parse fully qualified ISO timestamps; ambiguous locale dates stay text.
    if (/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(String(text))) {
      const value = Date.parse(text)/1000;
      return Number.isFinite(value) ? value : null;
    }
    return null;
  }
  function cardFor(el, pattern) {
    for(let node=el.parentElement, depth=0; node && depth<7; node=node.parentElement, depth++) {
      if(node.querySelectorAll('progress,[role="meter"]').length !== 1) break;
      if(pattern.test(node.innerText || node.textContent || '')) return node;
    }
    return null;
  }
  function parseDocument(doc, url) {
    const provider = providerForUrl(url);
    if(!provider) return null;
    const windows=[];
    if(provider==='codex') {
      for(const bar of doc.querySelectorAll('progress')) {
        if(!/剩余|remaining/i.test(bar.getAttribute('aria-label') || '')) continue;
        const card=cardFor(bar, /5\s*(?:小时|hour)|每周限额|weekly\s*(?:limit|usage)/i);
        if(!card || Number(bar.getAttribute('max'))!==100) continue;
        const text=card.innerText || card.textContent || '';
        const short=/5\s*(?:小时|hour)/i.test(text);
        const remaining=Number(bar.getAttribute('value'));
        if(bar.getAttribute('value')===null || !Number.isFinite(remaining) || remaining<0 || remaining>100) continue;
        const resetNode=[...card.querySelectorAll('[title],time[datetime]')].find(n=>absoluteReset(n.getAttribute('title') || n.getAttribute('datetime')));
        windows.push({key:short?'primary_window':'secondary_window', used:100-remaining,
          reset_at: resetNode?absoluteReset(resetNode.getAttribute('title') || resetNode.getAttribute('datetime')):null,
          reset_text: resetNode?(resetNode.innerText || resetNode.textContent || '').trim():''});
      }
    } else {
      for(const bar of doc.querySelectorAll('[role="meter"]')) {
        const label=(bar.getAttribute('aria-label') || (bar.getAttribute('aria-labelledby') || '').split(/\s+/).map(id=>doc.getElementById(id)?.textContent || '').join(' ')).trim();
        const short=/^(Current session|当前会话|本次会话)$/i.test(label);
        const weekly=/^(This week|All models|本周|所有模型)$/i.test(label);
        if(!short && !weekly) continue;
        const card=cardFor(bar, /Resets|重置/i);
        const raw=bar.getAttribute('aria-valuenow');
        const used=Number(raw);
        if(!card || raw===null || Number(bar.getAttribute('aria-valuemax'))!==100 || !Number.isFinite(used) || used<0 || used>100) continue;
        if(!/used|已用|已使用/i.test(bar.getAttribute('aria-valuetext') || '')) continue;
        const text=card.innerText || card.textContent || '';
        const resetText=(text.match(/Resets[^\n]*|[^\n]*重置[^\n]*/i)||[''])[0].trim();
        windows.push({key:short?'five_hour':'seven_day',used,reset_at:null,reset_text:resetText});
      }
    }
    if(new Set(windows.map(w=>w.key)).size!==windows.length) return {provider,status:'unrecognized',windows:[]};
    return {provider,status:windows.length?'ok':'unrecognized',windows};
  }
  const api={providerForUrl,absoluteReset,parseDocument};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  else root.UsageParser=api;
})(globalThis);
