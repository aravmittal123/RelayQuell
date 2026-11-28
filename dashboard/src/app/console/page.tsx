'use client';
import { useEffect, useState } from 'react';
import { Activity, Shield, Zap, Radio, ExternalLink, Unlock, Terminal, RefreshCw } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_GATEWAY_URL || 'http://localhost:8085';
type Event = {id:number;timestamp:number;type:string;agent_id:string;detail:string;data:Record<string,unknown>};
type State = {total_calls:number;blocked_calls:number;estimated_usd_saved:number;avg_eval_ms:number;quarantined_agents:Record<string,{reason:string;synced:boolean}>;flags:Record<string,unknown>;flagsmith_connected:boolean};
const initial: State = {total_calls:0,blocked_calls:0,estimated_usd_saved:0,avg_eval_ms:0,quarantined_agents:{},flags:{},flagsmith_connected:false};

export default function Page() {
  const [preview,setPreview] = useState<unknown>(null);
  const [state,setState] = useState<State>(initial);
  const [events,setEvents] = useState<Event[]>([]);
  const [connected,setConnected] = useState(false);
  const [busy,setBusy] = useState('');
  const [error,setError] = useState('');
  async function reload() {
    const response = await fetch(`${API}/api/state`);
    if (!response.ok) throw new Error(`State HTTP ${response.status}`);
    setState(await response.json());
  }
  useEffect(()=>{
    let live = true;
    const poll = () => reload().catch(e=>{if(live) setError(String(e));});
    poll();
    const timer=setInterval(poll,2000);
    const source=new EventSource(`${API}/api/events`);
    source.onopen=()=>setConnected(true);
    source.onerror=()=>setConnected(false);
    source.onmessage=e=>{const event:Event=JSON.parse(e.data);setEvents(old=>[event,...old.filter(x=>x.id!==event.id)].slice(0,160));};
    return ()=>{live=false;clearInterval(timer);source.close();};
  },[]);
  async function post(path:string,body:unknown) {
    const response=await fetch(`${API}${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response;
  }
  async function action(name:string,run:()=>Promise<unknown>) {
    setBusy(name);setError('');
    try {await run();await reload();} catch(e) {setError(String(e));} finally {setBusy('');}
  }
  async function tool(agent:string,args:Record<string,unknown>) {
    return fetch(`${API}/mcp`,{method:'POST',headers:{'Content-Type':'application/json','X-Agent-Id':agent},body:JSON.stringify({jsonrpc:'2.0',id:Date.now(),method:'tools/call',params:{name:'charge_card',arguments:args}})});
  }
  async function demo(runaway:boolean) {
    const agent=runaway?'agent_runaway':'agent_healthy';
    if(runaway) await post('/api/quarantine/release',{agent_id:agent});
    for(let i=0;i<(runaway?5:1);i++) {
      const response=await tool(agent,{order_id:runaway?'loop-order':crypto.randomUUID(),amount:5});
      if(!response.ok && response.status!==429) throw new Error(`Tool HTTP ${response.status}`);
    }
    const response=await fetch(`${API}/v1/chat/completions`,{method:'POST',headers:{'Content-Type':'application/json','X-Agent-Id':agent},body:JSON.stringify({messages:[{role:'user',content:'Report status'}]})});
    if(!response.ok) throw new Error(`LLM HTTP ${response.status}`);
  }
  const cards=[['Total intercepted calls',state.total_calls,Activity],['Blocked calls',state.blocked_calls,Shield],['Quarantined agents',Object.keys(state.quarantined_agents).length,Zap],['Estimated spend protected',`$${state.estimated_usd_saved.toFixed(4)}`,Shield]] as const;
  return <main>
    <header><a className="wordmark" href="/"><Shield size={28}/><span>VAEL<span className="cyan">TRIXIS</span></span></a><div className="header-right"><span className={connected?'live':'offline'}><Radio size={15}/> {connected?'TELEMETRY LIVE':'RECONNECTING'}</span><a href="http://localhost:8000" target="_blank" rel="noreferrer">Self-hosted Flagsmith <ExternalLink size={14}/></a></div></header>
    <section className="intro"><div><p className="eyebrow">RUNTIME DEFENSE / CONTROL PLANE</p><h1>Runtime operations.<br/><span>Policy in control.</span></h1><p className="subtitle">Detect the loop. Isolate the agent. Protect the rest.</p></div><div className="control"><span className="eyebrow">FLAGSMITH LOCAL EVALUATION</span><strong className="cyan">{state.avg_eval_ms.toFixed(3)}<small> ms</small></strong><span className={state.flagsmith_connected?'live':'offline'}>{state.flagsmith_connected?'Environment document connected':'Control plane unavailable'}</span><span className="muted">5-second polling · immediate refresh on trip</span></div></section>
    <section className="kpis">{cards.map(([label,value,Icon])=><article className="card" key={label}><div><span>{label}</span><Icon size={19}/></div><strong>{value}</strong></article>)}</section>
    <section className="trigger"><div><Terminal size={19}/><b>Run a live experiment</b><span className="muted">Zero API keys. Real control plane.</span></div><div className="buttons"><button disabled={!!busy} onClick={()=>action('healthy',()=>demo(false))}>Healthy call</button><button className="danger" disabled={!!busy} onClick={()=>action('runaway',()=>demo(true))}><Zap size={15}/> Trigger doom-loop</button><button disabled={!!busy} onClick={()=>action('refresh',()=>post('/api/policy/refresh',{}))}><RefreshCw size={15}/> Refresh policy</button></div></section>
    {busy&&<p role="status" className="cyan">Running {busy}…</p>}{error&&<p role="alert" className="error">{error}</p>}
    <section className="monitors">{['agent_healthy','agent_runaway'].map((agent,i)=><article className={`monitor ${i?'runaway':'healthy'}`} key={agent}><div className="monitor-title"><div><span className="eyebrow">{i?'BEHAVIORAL CONTAINMENT':'UNINTERRUPTED TRAFFIC'}</span><h2>{i?'Runaway agent':'Healthy agent'}</h2><code>{agent}</code></div><span className={state.quarantined_agents[agent]?'badge red':'badge green'}>{state.quarantined_agents[agent]?'CIRCUIT OPEN':'MONITORING'}</span></div><div className="feed" aria-live="polite">{events.filter(e=>e.agent_id===agent).map(e=><div className={`event ${['BLOCKED','TRIPPED','UPSTREAM_ERROR'].includes(e.type)?'bad':''}`} key={e.id}><time>{new Date(e.timestamp*1000).toLocaleTimeString()}</time><b>{e.type}</b><span>{e.detail}</span>{e.data.arguments!==undefined&&<code>{JSON.stringify(e.data.arguments)}</code>}</div>)}{!events.some(e=>e.agent_id===agent)&&<p className="empty">Awaiting traffic. Use the experiment controls above.</p>}</div></article>)}</section>
    <section className="panel"><div className="panel-title"><h2><Shield size={20}/> Quarantine registry</h2><span className="muted">Agent isolation · persisted in Flagsmith</span></div><div className="table-wrap"><table><thead><tr><th>Agent identifier</th><th>Trip reason</th><th>Control plane sync</th><th>Recovery</th></tr></thead><tbody>{Object.entries(state.quarantined_agents).map(([agent,item])=><tr key={agent}><td><code>{agent}</code></td><td>{item.reason.replaceAll('_',' ')}</td><td><span className={item.synced?'badge green':'badge red'}>{item.synced?'SYNCED':'PENDING / RETRYING'}</span></td><td><button disabled={!!busy} onClick={()=>action('release',()=>post('/api/quarantine/release',{agent_id:agent}))}><Unlock size={14}/> Release quarantine</button></td></tr>)}</tbody></table>{!Object.keys(state.quarantined_agents).length&&<p className="empty">No quarantined agents. All circuits are clear.</p>}</div></section>
    <section className="panel policy"><h2>Policy rehearsal</h2><p className="muted">Compare the active Flagsmith loop policy with a four-call threshold. This isolated trace never calls upstreams or writes flags.</p><button disabled={!!busy} onClick={()=>action('preview',async()=>{const response=await post('/api/policy/preview',{candidate_policy:{max_identical_calls:4},calls:['loop','healthy','loop','loop'].map((agent_id,i)=>({agent_id,at_seconds:i,tool:{name:'charge_card',arguments:{order_id:'replay'}}}))});setPreview(await response.json());})}>Compare loop policies</button> <a href={`${API}/api/incidents`} target="_blank" rel="noreferrer" className="muted">Session incident index</a>{preview!==null&&<pre>{JSON.stringify(preview,null,2)}</pre>}</section>
    <details className="panel policy"><summary>Live policy JSON <span className="muted">breaker_policy_config</span></summary><pre>{JSON.stringify(state.flags.policy||{},null,2)}</pre></details>
    <footer><span>VAELTRIXIS / RUNTIME CONTROL</span><span>Self-hosted. Locally evaluated. Human controlled.</span></footer>
  </main>;
}
