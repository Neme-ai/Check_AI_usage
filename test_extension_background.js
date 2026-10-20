const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
const parser=require('./chrome-extension/parser');
const state={token:'x'.repeat(43),monitors:{codex:2},lastReload:{codex:0},generation:'old',paused:false};
const tabs=new Map([[1,{id:1,url:'https://chatgpt.com/settings/usage',status:'complete'}],[2,{id:2,url:'https://chatgpt.com/settings/usage?tab=overview',status:'complete'}]]);
const calls=[],reloaded=[],listeners={};
const chrome={
 storage:{local:{get:async keys=>Object.fromEntries(keys.map(k=>[k,state[k]])),set:async data=>Object.assign(state,data)}},
 alarms:{get:async()=>({name:'usage-tick'}),create:async()=>{},onAlarm:{addListener:f=>listeners.alarm=f}},
 tabs:{get:async id=>{if(!tabs.has(id))throw Error('closed');return tabs.get(id);},reload:async id=>reloaded.push(id),onUpdated:{addListener:f=>listeners.updated=f},sendMessage:async()=>{}},
 runtime:{getURL:path=>'chrome-extension://'+'a'.repeat(32)+'/'+path,onMessage:{addListener:f=>listeners.message=f},onInstalled:{addListener:()=>{}},onStartup:{addListener:()=>{}}}
};
const context=vm.createContext({chrome,UsageParser:parser,importScripts:()=>{},AbortSignal,Date,URL,console,fetch:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({refresh:'new'})};}});
vm.runInContext(fs.readFileSync('chrome-extension/background.js','utf8'),context);
async function message(data,sender){return await new Promise(resolve=>listeners.message(data,sender,resolve));}
(async()=>{
 await vm.runInContext('tick()',context);assert.deepEqual(reloaded,[2]);
 const snapshot={provider:'codex',status:'ok',observed_at:Date.now()/1000,windows:[{key:'primary_window',used:30,reset_at:null,reset_text:'',cookie:'DO_NOT_SEND'}],password:'DO_NOT_SEND'};
 const before=calls.length;
 assert.equal((await message({type:'SNAPSHOT',snapshot},{tab:{id:1},frameId:0,url:tabs.get(1).url})).ok,false);
 assert.equal(calls.length,before);
 assert.equal((await message({type:'SNAPSHOT',snapshot},{tab:{id:2},frameId:0,url:tabs.get(2).url})).ok,true);
 const body=calls.at(-1).options.body;assert.ok(!body.includes('DO_NOT_SEND'));assert.ok(body.includes('"used":30'));
 tabs.get(2).url='https://chatgpt.com/c/private-chat';
 await vm.runInContext('tick(true)',context);assert.deepEqual(reloaded,[2]);
 assert.match(calls.at(-1).options.body,/wrong_page/);
 state.paused=true;const count=calls.length;await vm.runInContext('tick(true)',context);assert.equal(calls.length,count);
 console.log('Extension worker tests passed: own tabs only, payload allowlist, navigation guard and pause');
})().catch(error=>{console.error(error);process.exitCode=1;});
