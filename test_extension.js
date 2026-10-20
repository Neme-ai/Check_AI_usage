const assert=require('node:assert/strict');
const {JSDOM}=require('./build/test-tools/node_modules/jsdom');
const parser=require('./chrome-extension/parser');
function document(html){return new JSDOM(html).window.document;}
const codex=document(`<section><div>5 小时限额</div><div><span title="2026年10月20日星期二 GMT+8 15:26:16">4小时43分钟 后重置</span><span>剩余 62%</span><progress aria-label="剩余用量" max="100" value="62"></progress></div></section><section><div>每周限额</div><div><span title="2026年10月25日星期日 GMT+8 11:38:59">5天0小时 后重置</span><progress aria-label="剩余用量" max="100" value="77"></progress></div></section><div>自动充值 100%</div>`);
const c=parser.parseDocument(codex,'https://chatgpt.com/settings/usage?tab=overview');
assert.equal(c.windows.length,2);assert.equal(c.windows[0].used,38);assert.equal(c.windows[1].used,23);
assert.equal(c.windows[0].reset_at,Date.parse('2026-10-20T15:26:16+08:00')/1000);
const claude=document(`<section><span id="session">Current session</span><span>Resets at 3:20 PM</span><div role="meter" aria-labelledby="session" aria-valuemax="100" aria-valuenow="17" aria-valuetext="17% used"></div></section><section><span id="week">This week</span><span>Resets Friday 12:00 AM</span><div role="meter" aria-labelledby="week" aria-valuemax="100" aria-valuenow="75" aria-valuetext="75% used"></div></section><section><span id="cowork">Cowork</span><div role="meter" aria-labelledby="cowork" aria-valuemax="100" aria-valuenow="97" aria-valuetext="97%"></div></section>`);
const a=parser.parseDocument(claude,'https://claude.ai/new#settings/usage');
assert.equal(a.windows.length,2);assert.equal(a.windows[0].used,17);assert.equal(a.windows[1].used,75);
assert.equal(a.windows[1].reset_at,null);assert.match(a.windows[1].reset_text,/Resets Friday/);
assert.equal(parser.parseDocument(claude,'https://claude.ai/new'),null);
assert.equal(parser.providerForUrl('https://chatgpt.com.evil.example/settings/usage'),null);
assert.equal(parser.providerForUrl('http://chatgpt.com/settings/usage'),null);
assert.equal(parser.parseDocument(document('<div>购买额度 100%</div>'),'https://chatgpt.com/settings/usage').status,'unrecognized');
const bad=document('<section>5 小时限额<progress aria-label="剩余用量" max="100"></progress></section>');
assert.equal(parser.parseDocument(bad,'https://chatgpt.com/settings/usage').status,'unrecognized');
console.log('Extension DOM tests passed: observed quota structures, reset timezone, unrelated percentages, missing fields and URL boundaries');
