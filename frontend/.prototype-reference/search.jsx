// search.jsx — New Search flow with live progress + chat assistant

function NewSearch({ user, navigate }) {
  const [phase, setPhase] = useState('compose'); // compose | running | done
  const [messages, setMessages] = useState([
    { role: 'bot', text: window.ASSISTANT_GREETING },
  ]);
  const [draft, setDraft] = useState('');
  const [niche, setNiche] = useState('');
  const [region, setRegion] = useState('');
  const [profession, setProfession] = useState('web design & dev for small businesses');
  const [progress, setProgress] = useState(0);
  const [stageIdx, setStageIdx] = useState(0);
  const [foundCount, setFoundCount] = useState(0);
  const chatRef = useRef(null);

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages]);

  const sendMessage = (text) => {
    if (!text.trim()) return;
    const newMsgs = [...messages, { role: 'user', text }];
    setMessages(newMsgs);
    setDraft('');

    setTimeout(() => {
      // naive parse
      const lower = text.toLowerCase();
      const parsed = parseNicheRegion(text);
      if (parsed) {
        setNiche(parsed.niche);
        setRegion(parsed.region);
        setMessages(m => [...m, {
          role: 'bot',
          text: `Got it — searching for **${parsed.niche}** in **${parsed.region}**. Anything else I should know about your offer? Otherwise I'll kick off the search.`,
          confirm: true,
        }]);
      } else if (lower.includes('yes') || lower.includes('go') || lower.includes('run') || lower.includes('start')) {
        startSearch();
      } else {
        setMessages(m => [...m, { role: 'bot', text: 'Tell me the niche and the region, e.g. "roofing companies in New York".' }]);
      }
    }, 600);
  };

  const parseNicheRegion = (text) => {
    const m = text.match(/(.+?)\s+(in|at|around|near|,)\s+(.+)/i);
    if (m) return { niche: m[1].trim(), region: m[3].trim() };
    const parts = text.split(/[,]\s*/);
    if (parts.length === 2) return { niche: parts[0].trim(), region: parts[1].trim() };
    return null;
  };

  const startSearch = () => {
    if (!niche || !region) {
      setMessages(m => [...m, { role: 'bot', text: 'I still need a niche and a region — drop them in and I\'ll start.' }]);
      return;
    }
    setPhase('running');
    runProgress();
  };

  const runProgress = () => {
    let elapsed = 0;
    const total = window.PROGRESS_STAGES.reduce((a, s) => a + s.duration, 0);
    const interval = setInterval(() => {
      elapsed += 100;
      const pct = Math.min(99, Math.round((elapsed / total) * 100));
      setProgress(pct);
      // compute current stage
      let cum = 0;
      for (let i = 0; i < window.PROGRESS_STAGES.length; i++) {
        cum += window.PROGRESS_STAGES[i].duration;
        if (elapsed <= cum) { setStageIdx(i); break; }
      }
      // increment found
      if (elapsed > 2000 && elapsed < 8000) {
        setFoundCount(c => Math.min(48, c + Math.random() > 0.4 ? c + 1 : c));
      }
      if (elapsed >= total) {
        clearInterval(interval);
        setProgress(100);
        setStageIdx(window.PROGRESS_STAGES.length);
        setFoundCount(48);
        setTimeout(() => setPhase('done'), 500);
      }
    }, 100);
  };

  if (phase === 'compose') {
    return <ComposeView user={user} messages={messages} setMessages={setMessages}
                        draft={draft} setDraft={setDraft} sendMessage={sendMessage}
                        chatRef={chatRef}
                        niche={niche} setNiche={setNiche}
                        region={region} setRegion={setRegion}
                        profession={profession} setProfession={setProfession}
                        startSearch={startSearch} navigate={navigate} />;
  }
  if (phase === 'running') {
    return <RunningView niche={niche} region={region} progress={progress}
                        stageIdx={stageIdx} foundCount={foundCount} navigate={navigate} />;
  }
  return <DoneView niche={niche} region={region} navigate={navigate} />;
}

function ComposeView({ user, messages, draft, setDraft, sendMessage, chatRef,
                      niche, setNiche, region, setRegion, profession, setProfession,
                      startSearch, navigate }) {
  return (
    <>
      <Topbar crumbs={[{label:'Workspace', href:'/app'}, {label:'New search'}]}
              right={<button className="btn btn-ghost btn-sm" onClick={()=>navigate('/app')}>Cancel</button>} />
      <div className="page" style={{display:'grid', gridTemplateColumns:'1.2fr 1fr', gap:24, maxWidth:1200}}>
        {/* left — chat assistant */}
        <div className="card" style={{padding:0, display:'flex', flexDirection:'column', height:'calc(100vh - 140px)', minHeight:520}}>
          <div style={{padding:'18px 22px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', gap:12}}>
            <div style={{width:32, height:32, borderRadius:'50%', background:'linear-gradient(135deg, var(--accent), #EC4899)', display:'grid', placeItems:'center', color:'white'}}>
              <Icon name="sparkles" size={16}/>
            </div>
            <div>
              <div style={{fontSize:14, fontWeight:600}}>Lumen</div>
              <div style={{fontSize:11, color:'var(--text-muted)'}}><span className="status-dot live" style={{marginRight:6, width:6, height:6}}></span>Your search copilot</div>
            </div>
          </div>

          <div ref={chatRef} style={{flex:1, overflowY:'auto', padding:'20px 22px', display:'flex', flexDirection:'column', gap:14}}>
            {messages.map((m, i) => <ChatBubble key={i} msg={m} user={user} />)}
            {messages.length <= 2 && (
              <div style={{marginTop:8}}>
                <div className="eyebrow" style={{marginBottom:10, fontSize:10}}>Try one of these</div>
                <div style={{display:'flex', flexDirection:'column', gap:6}}>
                  {window.ASSISTANT_QUICK_PROMPTS.map(p => (
                    <button key={p} className="btn btn-ghost btn-sm" onClick={()=>sendMessage(p)} style={{justifyContent:'flex-start'}}>
                      <Icon name="arrow" size={13}/>{p}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div style={{padding:'14px 16px', borderTop:'1px solid var(--border)', display:'flex', gap:8}}>
            <input className="input" value={draft}
                   onChange={e=>setDraft(e.target.value)}
                   onKeyDown={e=>{ if(e.key==='Enter') sendMessage(draft); }}
                   placeholder="Describe who you're looking for…" />
            <button className="btn btn-icon" onClick={()=>sendMessage(draft)} style={{background:'var(--accent)', color:'white', width:40, height:40}}>
              <Icon name="send" size={16}/>
            </button>
          </div>
        </div>

        {/* right — structured form */}
        <div>
          <div className="eyebrow" style={{marginBottom:6}}>Search parameters</div>
          <div style={{fontSize:24, fontWeight:600, letterSpacing:'-0.02em', marginBottom:4}}>Or set it manually</div>
          <div style={{fontSize:13, color:'var(--text-muted)', marginBottom:24}}>Lumen auto-fills these as you chat.</div>

          <div style={{display:'flex', flexDirection:'column', gap:16}}>
            <div>
              <label style={{fontSize:12, fontWeight:600, color:'var(--text-muted)', marginBottom:6, display:'block'}}>Niche</label>
              <input className="input" value={niche} onChange={e=>setNiche(e.target.value)} placeholder="roofing companies" />
            </div>
            <div>
              <label style={{fontSize:12, fontWeight:600, color:'var(--text-muted)', marginBottom:6, display:'block'}}>Region</label>
              <input className="input" value={region} onChange={e=>setRegion(e.target.value)} placeholder="New York, NY" />
            </div>
            <div>
              <label style={{fontSize:12, fontWeight:600, color:'var(--text-muted)', marginBottom:6, display:'block'}}>Your offer (for AI scoring)</label>
              <textarea className="textarea" value={profession} onChange={e=>setProfession(e.target.value)} rows={3}
                        placeholder="e.g. I build SEO-optimized websites for local contractors"/>
              <div style={{fontSize:11.5, color:'var(--text-dim)', marginTop:6}}>Claude uses this to personalize every score and pitch.</div>
            </div>

            <div style={{display:'flex', alignItems:'center', gap:10, padding:'14px 16px', background:'var(--surface-2)', borderRadius:10, border:'1px solid var(--border)'}}>
              <Icon name="zap" size={18} style={{color:'var(--warm)'}} />
              <div style={{fontSize:12.5, color:'var(--text-muted)', flex:1}}>Up to 50 leads · avg 90 seconds · Excel included</div>
            </div>

            <button className="btn btn-lg" disabled={!niche || !region} onClick={startSearch}
                    style={{justifyContent:'center', marginTop:8, opacity: (!niche || !region) ? 0.5 : 1}}>
              <Icon name="sparkles" size={16}/> Launch search
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function ChatBubble({ msg, user }) {
  const isBot = msg.role === 'bot';
  return (
    <div style={{display:'flex', gap:10, alignItems:'flex-start', flexDirection: isBot ? 'row' : 'row-reverse'}}>
      {isBot ? (
        <div style={{width:28, height:28, borderRadius:'50%', background:'linear-gradient(135deg, var(--accent), #EC4899)', display:'grid', placeItems:'center', color:'white', flexShrink:0}}>
          <Icon name="sparkles" size={13}/>
        </div>
      ) : (
        <div className="avatar avatar-sm" style={{background: user.color}}>{user.initials}</div>
      )}
      <div style={{
        maxWidth:'78%', padding:'10px 14px',
        background: isBot ? 'var(--surface-2)' : 'var(--accent)',
        color: isBot ? 'var(--text)' : 'white',
        border: isBot ? '1px solid var(--border)' : 'none',
        borderRadius: 14,
        borderTopLeftRadius: isBot ? 4 : 14,
        borderTopRightRadius: isBot ? 14 : 4,
        fontSize:13.5, lineHeight:1.5,
      }}>
        {msg.text.split('**').map((part, i) => i % 2 === 1 ? <b key={i}>{part}</b> : part)}
      </div>
    </div>
  );
}

function RunningView({ niche, region, progress, stageIdx, foundCount, navigate }) {
  return (
    <>
      <Topbar crumbs={[{label:'Workspace', href:'/app'}, {label:'Search in progress'}]} />
      <div className="page" style={{maxWidth:900}}>
        <div className="card" style={{padding:'40px 44px', position:'relative', overflow:'hidden'}}>
          <div className="mesh-bg" style={{opacity:0.5}}></div>
          <div className="hud-corner tl"/><div className="hud-corner tr"/><div className="hud-corner bl"/><div className="hud-corner br"/>

          <div style={{position:'relative'}}>
            <div className="eyebrow" style={{marginBottom:14}}>
              <span className="status-dot live" style={{marginRight:8}}></span>Searching
            </div>
            <div style={{fontSize:36, fontWeight:700, letterSpacing:'-0.02em', lineHeight:1.05, marginBottom:12, maxWidth:600}}>
              {niche} <span style={{fontStyle:'italic', fontWeight:400, color:'var(--text-muted)'}}>in</span> {region}
            </div>
            <div style={{fontSize:14, color:'var(--text-muted)', marginBottom:32}}>
              This usually takes 60–120 seconds. You'll get an email and a notification when it's ready.
            </div>

            {/* big progress ring */}
            <div style={{display:'grid', gridTemplateColumns:'220px 1fr', gap:40, alignItems:'center'}}>
              <ProgressRing progress={progress} found={foundCount} />
              <div style={{display:'flex', flexDirection:'column', gap:10}}>
                {window.PROGRESS_STAGES.map((s, i) => {
                  const done = i < stageIdx;
                  const current = i === stageIdx;
                  return (
                    <div key={s.key} style={{
                      display:'flex', alignItems:'center', gap:14,
                      padding:'12px 14px', borderRadius:10,
                      background: current ? 'var(--accent-soft)' : 'transparent',
                      border: current ? '1px solid color-mix(in srgb, var(--accent) 20%, transparent)' : '1px solid transparent',
                      opacity: !done && !current ? 0.4 : 1,
                      transition:'all .3s',
                    }}>
                      <div style={{
                        width:26, height:26, borderRadius:'50%', flexShrink:0,
                        background: done ? 'var(--hot)' : current ? 'var(--accent)' : 'var(--surface-2)',
                        color: (done||current) ? 'white' : 'var(--text-dim)',
                        display:'grid', placeItems:'center',
                        border: !done && !current ? '1px dashed var(--border-strong)' : 'none',
                        fontSize:11, fontWeight:600, fontFamily:'var(--font-mono)',
                      }}>
                        {done ? <Icon name="check" size={14}/> : current ? <SpinnerDot/> : String(i+1).padStart(2,'0')}
                      </div>
                      <div style={{flex:1}}>
                        <div style={{fontSize:14, fontWeight:600, color: !done && !current ? 'var(--text-muted)' : 'var(--text)'}}>{s.label}</div>
                        <div style={{fontSize:12, color:'var(--text-muted)', marginTop:2}}>{s.detail}</div>
                      </div>
                      {current && <div className="shimmer-line" style={{width:60}}></div>}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* live cards stream */}
        {foundCount > 0 && (
          <div style={{marginTop:24}}>
            <div className="eyebrow" style={{marginBottom:12}}>Leads found — {foundCount}</div>
            <div style={{display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:10}}>
              {window.MOCK_LEADS.slice(0, Math.min(foundCount, 6)).map((l, i) => (
                <div key={l.id} className="card fade-up" style={{padding:12, animationDelay: (i * 80) + 'ms'}}>
                  <div style={{display:'flex', alignItems:'center', gap:8, marginBottom:6}}>
                    <span className={'status-dot ' + l.temp}></span>
                    <div style={{fontSize:13, fontWeight:600, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1}}>{l.name}</div>
                  </div>
                  <div style={{fontSize:11, color:'var(--text-muted)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>{l.address}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function ProgressRing({ progress, found }) {
  const R = 90;
  const C = 2 * Math.PI * R;
  return (
    <div style={{position:'relative', width:220, height:220, margin:'0 auto'}}>
      <svg width="220" height="220" style={{transform:'rotate(-90deg)'}}>
        <circle cx="110" cy="110" r={R} fill="none" stroke="var(--border)" strokeWidth="2"/>
        <circle cx="110" cy="110" r={R} fill="none" stroke="var(--accent)" strokeWidth="3"
                strokeLinecap="round"
                strokeDasharray={C}
                strokeDashoffset={C - (C * progress / 100)}
                style={{transition:'stroke-dashoffset .4s'}}/>
        {/* tick marks */}
        {Array.from({length:60}).map((_, i) => {
          const angle = (i / 60) * 2 * Math.PI;
          const r1 = R + 10, r2 = R + 16;
          return <line key={i}
            x1={110 + Math.cos(angle) * r1} y1={110 + Math.sin(angle) * r1}
            x2={110 + Math.cos(angle) * r2} y2={110 + Math.sin(angle) * r2}
            stroke="var(--border-strong)" strokeWidth={i % 5 === 0 ? 1.5 : 0.6}/>;
        })}
      </svg>
      <div style={{position:'absolute', inset:0, display:'grid', placeItems:'center'}}>
        <div style={{textAlign:'center'}}>
          <div style={{fontFamily:'var(--font-mono)', fontSize:44, fontWeight:700, letterSpacing:'-0.02em', color:'var(--accent)'}}>{progress}%</div>
          <div className="eyebrow" style={{fontSize:10, marginTop:2}}>{found} leads found</div>
        </div>
      </div>
    </div>
  );
}

function SpinnerDot() {
  return <span style={{
    width:8, height:8, borderRadius:'50%', background:'white',
    animation:'livePulse 1s ease-in-out infinite',
  }}/>;
}

function DoneView({ niche, region, navigate }) {
  // fake completed session — use s-001
  return (
    <>
      <Topbar crumbs={[{label:'Workspace', href:'/app'}, {label:'Search complete'}]} />
      <div className="page" style={{maxWidth:900}}>
        <div className="card" style={{padding:'40px 44px', textAlign:'center', position:'relative', overflow:'hidden'}}>
          <div className="mesh-bg"></div>
          <div style={{position:'relative'}}>
            <div style={{width:64, height:64, borderRadius:'50%', background:'var(--hot)', display:'grid', placeItems:'center', margin:'0 auto 20px', color:'white'}}>
              <Icon name="check" size={32}/>
            </div>
            <div style={{fontSize:36, fontWeight:700, letterSpacing:'-0.02em', marginBottom:12}}>48 leads, ready.</div>
            <div style={{fontSize:15, color:'var(--text-muted)', marginBottom:32, maxWidth:440, margin:'0 auto 32px'}}>
              <b>9 hot</b>, <b>22 warm</b>, <b>17 cold</b> — each scored against your profile with a custom pitch.
            </div>
            <div style={{display:'flex', gap:10, justifyContent:'center'}}>
              <button className="btn btn-lg" onClick={()=>navigate('/app/session/s-001')}>
                Open results <Icon name="arrow" size={15}/>
              </button>
              <button className="btn btn-ghost btn-lg"><Icon name="download" size={15}/> Excel</button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

window.NewSearch = NewSearch;
