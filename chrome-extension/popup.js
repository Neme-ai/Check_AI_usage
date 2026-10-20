const message=document.getElementById('message');
async function send(data){
  try{const result=await chrome.runtime.sendMessage(data);message.textContent=result.ok?'操作完成':result.error||'操作失败';await showStatus();}
  catch(_){message.textContent='扩展服务不可用，请重新加载扩展';}
}
async function showStatus(){
  const s=await chrome.storage.local.get(['connection','status_codex','status_claude','paused']);
  document.getElementById('pause').checked=!!s.paused;
  document.getElementById('last').textContent=[s.connection||'尚未配对','Codex：'+(s.status_codex||'待打开监控页'),'Claude：'+(s.status_claude||'待打开监控页')].join('\n');
}
document.getElementById('pair').onclick=()=>send({type:'PAIR',token:document.getElementById('token').value.trim()});
document.getElementById('codex').onclick=()=>send({type:'OPEN',provider:'codex'});
document.getElementById('claude').onclick=()=>send({type:'OPEN',provider:'claude'});
document.getElementById('refresh').onclick=()=>send({type:'REFRESH'});
document.getElementById('pause').onchange=event=>send({type:'PAUSE',paused:event.target.checked});
showStatus();
