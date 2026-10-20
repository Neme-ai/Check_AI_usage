(() => {
  let sending=false;
  async function collect() {
    if(sending) return;
    const ready=await chrome.runtime.sendMessage({type:'IS_MONITOR'}).catch(()=>null);
    if(!ready?.enabled) return;
    sending=true;
    let snapshot=null;
    let previous='';
    // Wait for the real SPA quota cards, not a loading skeleton.
    for(let attempt=0;attempt<40;attempt++) {
      snapshot=UsageParser.parseDocument(document,location.href);
      const signature=snapshot?.status==='ok'?JSON.stringify(snapshot.windows):'';
      if(signature && signature===previous) break;
      previous=signature;
      await new Promise(resolve=>setTimeout(resolve,500));
    }
    if(snapshot) await chrome.runtime.sendMessage({type:'SNAPSHOT',snapshot:{...snapshot,observed_at:Date.now()/1000}}).catch(()=>{});
    sending=false;
  }
  chrome.runtime.onMessage.addListener(message=>{if(message.type==='COLLECT') collect();});
  collect();
})();
