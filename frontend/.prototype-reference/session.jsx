// session.jsx — Session Detail (one search with all its leads) + Leads CRM + Profile/Team/Settings

// ─── Session Detail ─────────────────────────────────────────────────
function SessionDetail({ user, navigate, sessionId }) {
  const session = window.MOCK_SESSIONS.find(s => s.id === sessionId) || window.MOCK_SESSIONS[0];
  const leads = window.MOCK_LEADS.filter(l => l.sessionId === session.id);
  const [activeLead, setActiveLead] = useState(null);
  const [filter, setFilter] = useState('all');

  const filtered = filter === 'all' ? leads : leads.filter(l => l.temp === filter);

  return (
    <>
      <Topbar crumbs={[{label:'Workspace', href:'/app'}, {label:'Sessions', href:'/app/sessions'}, {label: session.niche}]}
              right={<><button className="btn btn-ghost btn-sm"><Icon name="download" size={14}/>Excel</button><button className="btn btn-sm"><Icon name="plus" size={14}/>Add to CRM</button></>} />
      <div className="page">
        <div style={{display:'grid', gridTemplateColumns:'1fr auto auto auto auto', gap:16, marginBottom:24, alignItems:'center'}}>
          <div>
            <div className="eyebrow" style={{marginBottom:6}}><Icon name="mapPin" size={11} style={{verticalAlign:'-2px', marginRight:4}}/>{session.region}</div>
            <div style={{fontSize:38, fontWeight:700, letterSpacing:'-0.025em', lineHeight:1.05}}>{session.niche}</div>
            <div style={{display:'flex', gap:10, marginTop:10}}>
              {session.tags?.map(t => <span key={t} className="chip">{t}</span>)}
            </div>
          </div>
          {[{n:session.leadsTotal, l:'total', c:'var(--text)'},{n:session.hot, l:'hot', c:'var(--hot)'},{n:session.warm, l:'warm', c:'#B45309'},{n:session.cold, l:'cold', c:'var(--cold)'}].map((s,i)=>(
            <div key={i} style={{textAlign:'right', minWidth:70}}>
              <div style={{fontSize:28, fontWeight:700, color:s.c, fontFamily:'var(--font-mono)', letterSpacing:'-0.02em'}}>{s.n}</div>
              <div className="eyebrow" style={{fontSize:10}}>{s.l}</div>
            </div>
          ))}
        </div>

        {/* insights strip */}
        <div className="card" style={{padding:'20px 24px', marginBottom:20, background:'linear-gradient(135deg, var(--surface), color-mix(in srgb, var(--accent) 4%, var(--surface)))', border:'1px solid color-mix(in srgb, var(--accent) 20%, var(--border))'}}>
          <div style={{display:'flex', alignItems:'flex-start', gap:14}}>
            <div style={{width:36, height:36, borderRadius:10, background:'var(--accent-soft)', display:'grid', placeItems:'center', color:'var(--accent)', flexShrink:0}}>
              <Icon name="sparkles" size={18}/>
            </div>
            <div style={{flex:1}}>
              <div className="eyebrow" style={{marginBottom:4, color:'var(--accent)'}}>AI market insight</div>
              <div style={{fontSize:15, lineHeight:1.55, color:'var(--text)', maxWidth:820}}>
                NYC roofing market is saturated but <b>8 out of 9 hot leads lack online booking</b> — your instant-quote bundle is a perfect fit. Prioritize Northstar, Apex Urban, and Skyline Roof Systems: all three have strong review profiles and clear weak spots you can close in a 30-day pilot.
              </div>
            </div>
          </div>
        </div>

        <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:14}}>
          <div className="seg">
            <button className={filter==='all'?'active':''} onClick={()=>setFilter('all')}>All · {leads.length}</button>
            <button className={filter==='hot'?'active':''} onClick={()=>setFilter('hot')}><span className="status-dot hot" style={{marginRight:6}}></span>Hot</button>
            <button className={filter==='warm'?'active':''} onClick={()=>setFilter('warm')}><span className="status-dot warm" style={{marginRight:6}}></span>Warm</button>
            <button className={filter==='cold'?'active':''} onClick={()=>setFilter('cold')}><span className="status-dot cold" style={{marginRight:6}}></span>Cold</button>
          </div>
          <div style={{display:'flex', gap:8}}>
            <button className="btn btn-ghost btn-sm"><Icon name="filter" size={14}/>Filter</button>
            <button className="btn btn-ghost btn-sm"><Icon name="sortDesc" size={14}/>Score</button>
          </div>
        </div>

        <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(320px, 1fr))', gap:14}}>
          {filtered.map(l => <LeadCard key={l.id} lead={l} onClick={()=>setActiveLead(l)} />)}
        </div>
      </div>

      {activeLead && <LeadDetailModal lead={activeLead} onClose={()=>setActiveLead(null)} />}
    </>
  );
}

function LeadCard({ lead, onClick }) {
  return (
    <div className="card card-hover" onClick={onClick} style={{cursor:'pointer'}}>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:12}}>
        <div className={'chip chip-' + lead.temp}><span className={'status-dot ' + lead.temp}></span>{lead.temp}</div>
        <div style={{display:'flex', alignItems:'baseline', gap:4}}>
          <div style={{fontFamily:'var(--font-mono)', fontSize:26, fontWeight:700, letterSpacing:'-0.02em', color: lead.score>=75?'var(--hot)':lead.score>=50?'#B45309':'var(--cold)'}}>{lead.score}</div>
          <div style={{fontSize:11, color:'var(--text-dim)'}}>/100</div>
        </div>
      </div>
      <div style={{fontSize:15, fontWeight:600, marginBottom:4, letterSpacing:'-0.005em'}}>{lead.name}</div>
      <div style={{fontSize:12, color:'var(--text-muted)', marginBottom:10, display:'flex', alignItems:'center', gap:6}}>
        <Icon name="star" size={12} style={{color:'var(--warm)'}}/> {lead.rating} · {lead.reviews} reviews
      </div>
      <div style={{fontSize:13, color:'var(--text-muted)', lineHeight:1.5, display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical', overflow:'hidden', marginBottom:12}}>
        {lead.summary}
      </div>
      <div className="score-track"><div className={'score-fill ' + lead.temp} style={{width: lead.score + '%'}}></div></div>
      <div style={{display:'flex', gap:6, marginTop:12, flexWrap:'wrap'}}>
        {lead.phone && <span className="chip" style={{fontSize:11}}><Icon name="phone" size={10}/>phone</span>}
        {lead.website && <span className="chip" style={{fontSize:11}}><Icon name="globe" size={10}/>site</span>}
        {lead.socials && Object.keys(lead.socials).length > 0 && <span className="chip" style={{fontSize:11}}><Icon name="users" size={10}/>{Object.keys(lead.socials).length} social</span>}
      </div>
    </div>
  );
}

function LeadDetailModal({ lead, onClose }) {
  const [note, setNote] = useState('');
  const [status, setStatus] = useState(lead.status);
  return (
    <div style={{position:'fixed', inset:0, background:'rgba(15,15,20,0.4)', zIndex:100, display:'flex', alignItems:'center', justifyContent:'center', padding:30}} onClick={onClose}>
      <div onClick={e=>e.stopPropagation()} style={{background:'var(--surface)', borderRadius:16, width:'100%', maxWidth:880, maxHeight:'90vh', overflow:'auto', boxShadow:'var(--shadow-lg)'}}>
        <div style={{padding:'24px 28px', borderBottom:'1px solid var(--border)', display:'flex', justifyContent:'space-between', alignItems:'flex-start', position:'sticky', top:0, background:'var(--surface)', zIndex:2}}>
          <div>
            <div style={{display:'flex', alignItems:'center', gap:10, marginBottom:6}}>
              <div className={'chip chip-' + lead.temp}><span className={'status-dot ' + lead.temp}></span>{lead.temp} lead</div>
              <span className="chip">{lead.size} business</span>
            </div>
            <div style={{fontSize:26, fontWeight:700, letterSpacing:'-0.02em'}}>{lead.name}</div>
            <div style={{fontSize:13, color:'var(--text-muted)', marginTop:4}}>{lead.category} · {lead.address}</div>
          </div>
          <div style={{display:'flex', alignItems:'center', gap:16}}>
            <div style={{textAlign:'right'}}>
              <div style={{fontFamily:'var(--font-mono)', fontSize:36, fontWeight:700, color: lead.score>=75?'var(--hot)':lead.score>=50?'#B45309':'var(--cold)', letterSpacing:'-0.02em'}}>{lead.score}</div>
              <div className="eyebrow" style={{fontSize:10}}>AI score</div>
            </div>
            <button className="btn-icon" onClick={onClose}><Icon name="x" size={18}/></button>
          </div>
        </div>

        <div style={{padding:'24px 28px', display:'grid', gridTemplateColumns:'1.4fr 1fr', gap:28}}>
          <div>
            {/* AI advice */}
            <div className="card" style={{padding:20, background:'var(--accent-soft)', border:'1px solid color-mix(in srgb, var(--accent) 20%, transparent)', marginBottom:18}}>
              <div className="eyebrow" style={{color:'var(--accent)', marginBottom:8}}><Icon name="sparkles" size={11} style={{marginRight:4, verticalAlign:'-2px'}}/>How to pitch this lead</div>
              <div style={{fontSize:14, lineHeight:1.6, color:'var(--text)'}}>{lead.advice}</div>
            </div>

            <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:14, marginBottom:18}}>
              <div>
                <div className="eyebrow" style={{marginBottom:8, color:'var(--hot)'}}>Strengths</div>
                <ul style={{margin:0, paddingLeft:18, fontSize:13.5, lineHeight:1.65, color:'var(--text)'}}>
                  {lead.strengths.map((s,i)=>(<li key={i} style={{marginBottom:4}}>{s}</li>))}
                </ul>
              </div>
              <div>
                <div className="eyebrow" style={{marginBottom:8, color:'#B45309'}}>Weaknesses</div>
                <ul style={{margin:0, paddingLeft:18, fontSize:13.5, lineHeight:1.65, color:'var(--text)'}}>
                  {lead.weaknesses.map((s,i)=>(<li key={i} style={{marginBottom:4}}>{s}</li>))}
                </ul>
              </div>
            </div>
            {lead.redFlags.length > 0 && (
              <div style={{padding:14, background:'color-mix(in srgb, var(--cold) 5%, transparent)', border:'1px solid color-mix(in srgb, var(--cold) 20%, transparent)', borderRadius:10, marginBottom:18}}>
                <div className="eyebrow" style={{color:'var(--cold)', marginBottom:6}}>Red flags</div>
                <ul style={{margin:0, paddingLeft:18, fontSize:13, color:'var(--text-muted)'}}>
                  {lead.redFlags.map((s,i)=>(<li key={i}>{s}</li>))}
                </ul>
              </div>
            )}

            <div>
              <div className="eyebrow" style={{marginBottom:8}}>Notes</div>
              <textarea className="textarea" value={note} onChange={e=>setNote(e.target.value)} placeholder="Add your notes about this lead…" rows={3}/>
            </div>
          </div>

          <div>
            <div className="card" style={{padding:18, marginBottom:14}}>
              <div className="eyebrow" style={{marginBottom:10}}>Status</div>
              <div style={{display:'flex', flexDirection:'column', gap:6}}>
                {['new','contacted','replied','won','archived'].map(s => (
                  <div key={s} onClick={()=>setStatus(s)} style={{
                    padding:'9px 12px', borderRadius:8, cursor:'pointer', fontSize:13,
                    display:'flex', alignItems:'center', gap:10,
                    background: status===s?'var(--accent-soft)':'transparent',
                    color: status===s?'var(--accent)':'var(--text-muted)',
                    fontWeight: status===s?600:500,
                  }}>
                    <span style={{width:8, height:8, borderRadius:'50%', background: status===s?'var(--accent)':'var(--border-strong)'}}></span>
                    {s}
                  </div>
                ))}
              </div>
            </div>

            <div className="card" style={{padding:18}}>
              <div className="eyebrow" style={{marginBottom:10}}>Contact</div>
              <div style={{display:'flex', flexDirection:'column', gap:10, fontSize:13}}>
                {lead.phone && <div style={{display:'flex', alignItems:'center', gap:10, color:'var(--text)'}}><Icon name="phone" size={14} style={{color:'var(--text-muted)'}}/>{lead.phone}</div>}
                {lead.website && <div style={{display:'flex', alignItems:'center', gap:10, color:'var(--text)'}}><Icon name="globe" size={14} style={{color:'var(--text-muted)'}}/>{lead.website}</div>}
                {lead.email && <div style={{display:'flex', alignItems:'center', gap:10, color:'var(--text)'}}><Icon name="mail" size={14} style={{color:'var(--text-muted)'}}/>{lead.email}</div>}
                <div style={{display:'flex', alignItems:'center', gap:10, color:'var(--text-muted)'}}><Icon name="mapPin" size={14}/>{lead.address}</div>
                {lead.socials && Object.keys(lead.socials).length > 0 && (
                  <div style={{borderTop:'1px solid var(--border)', paddingTop:10, marginTop:4, display:'flex', gap:6, flexWrap:'wrap'}}>
                    {Object.entries(lead.socials).map(([k,v])=>(<span key={k} className="chip" style={{fontSize:11}}>{k}: {v}</span>))}
                  </div>
                )}
                <div style={{borderTop:'1px solid var(--border)', paddingTop:10, marginTop:4, display:'flex', alignItems:'center', gap:10}}>
                  <Icon name="star" size={14} style={{color:'var(--warm)'}}/>
                  <b>{lead.rating}</b> · {lead.reviews} reviews
                </div>
              </div>
            </div>

            <div style={{display:'flex', gap:8, marginTop:14}}>
              <button className="btn" style={{flex:1, justifyContent:'center'}}>Save changes</button>
              <button className="btn btn-ghost" title="Assign"><Icon name="users" size={14}/></button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Sessions list ───────────────────────────────────────────────────
function SessionsList({ navigate }) {
  return (
    <>
      <Topbar title="Sessions" subtitle="Every search your team has launched"
              right={<button className="btn" onClick={()=>navigate('/app/search')}><Icon name="plus" size={14}/>New search</button>} />
      <div className="page">
        <div style={{display:'flex', flexDirection:'column', gap:10}}>
          {window.MOCK_SESSIONS.map(s => <SessionRow key={s.id} session={s} navigate={navigate}/>)}
        </div>
      </div>
    </>
  );
}

// ─── All Leads CRM ───────────────────────────────────────────────────
function LeadsCRM({ navigate }) {
  const [view, setView] = useState('list');
  const [filter, setFilter] = useState('all');
  const [activeLead, setActiveLead] = useState(null);
  const leads = window.MOCK_LEADS;
  const filtered = filter === 'all' ? leads : leads.filter(l => l.status === filter || l.temp === filter);

  return (
    <>
      <Topbar title="All leads" subtitle={`${leads.length} leads across ${window.MOCK_SESSIONS.length} sessions`}
              right={<><button className="btn btn-ghost btn-sm"><Icon name="download" size={14}/>Export</button></>} />
      <div className="page">
        <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:16, gap:12}}>
          <div className="seg">
            {['all','new','contacted','replied','won','archived'].map(s => (
              <button key={s} className={filter===s?'active':''} onClick={()=>setFilter(s)}>
                {s} · {s==='all'?leads.length:leads.filter(l=>l.status===s).length}
              </button>
            ))}
          </div>
          <div className="seg">
            <button className={view==='list'?'active':''} onClick={()=>setView('list')}><Icon name="list" size={14}/></button>
            <button className={view==='kanban'?'active':''} onClick={()=>setView('kanban')}><Icon name="kanban" size={14}/></button>
            <button className={view==='grid'?'active':''} onClick={()=>setView('grid')}><Icon name="grid" size={14}/></button>
          </div>
        </div>

        {view === 'list' && (
          <div className="card" style={{padding:0, overflow:'hidden'}}>
            <table className="tbl">
              <thead><tr>
                <th></th><th>Lead</th><th>Session</th><th>Score</th><th>Status</th><th>Owner</th><th>Last touched</th><th></th>
              </tr></thead>
              <tbody>
                {filtered.map(l => {
                  const owner = l.owner ? window.MOCK_TEAM.find(u=>u.id===l.owner) : null;
                  return (
                    <tr key={l.id} style={{cursor:'pointer'}} onClick={()=>setActiveLead(l)}>
                      <td style={{width:24}}><span className={'status-dot ' + l.temp}></span></td>
                      <td>
                        <div style={{fontSize:13.5, fontWeight:600}}>{l.name}</div>
                        <div style={{fontSize:11.5, color:'var(--text-muted)'}}>{l.address}</div>
                      </td>
                      <td><span className="chip" style={{fontSize:11}}>Roofing · NYC</span></td>
                      <td><span style={{fontFamily:'var(--font-mono)', fontWeight:700, color: l.score>=75?'var(--hot)':l.score>=50?'#B45309':'var(--cold)'}}>{l.score}</span></td>
                      <td><span className="chip" style={{fontSize:11}}>{l.status}</span></td>
                      <td>{owner ? <div style={{display:'flex', alignItems:'center', gap:8}}><div className="avatar avatar-sm" style={{background:owner.color}}>{owner.initials}</div><span style={{fontSize:12.5}}>{owner.name}</span></div> : <span style={{color:'var(--text-dim)', fontSize:12}}>—</span>}</td>
                      <td style={{fontSize:12, color:'var(--text-muted)'}}>{l.lastTouched || '—'}</td>
                      <td><Icon name="chevronRight" size={14} style={{color:'var(--text-dim)'}}/></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {view === 'kanban' && (
          <div style={{display:'grid', gridTemplateColumns:'repeat(5, 1fr)', gap:14}}>
            {['new','contacted','replied','won','archived'].map(col => {
              const items = leads.filter(l => l.status === col);
              return (
                <div key={col} style={{background:'var(--surface-2)', borderRadius:12, padding:12, minHeight:400}}>
                  <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:12, padding:'0 4px'}}>
                    <div style={{fontSize:12, fontWeight:600, textTransform:'capitalize'}}>{col}</div>
                    <div className="chip" style={{fontSize:11, background:'var(--surface)'}}>{items.length}</div>
                  </div>
                  <div style={{display:'flex', flexDirection:'column', gap:8}}>
                    {items.map(l => (
                      <div key={l.id} className="card" style={{padding:12, cursor:'pointer'}} onClick={()=>setActiveLead(l)}>
                        <div style={{display:'flex', justifyContent:'space-between', marginBottom:6}}>
                          <span className={'status-dot ' + l.temp}></span>
                          <span style={{fontFamily:'var(--font-mono)', fontSize:12, fontWeight:700, color:l.score>=75?'var(--hot)':'#B45309'}}>{l.score}</span>
                        </div>
                        <div style={{fontSize:13, fontWeight:600, marginBottom:4}}>{l.name}</div>
                        <div style={{fontSize:11, color:'var(--text-muted)'}}>{l.address}</div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {view === 'grid' && (
          <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(280px, 1fr))', gap:14}}>
            {filtered.map(l => <LeadCard key={l.id} lead={l} onClick={()=>setActiveLead(l)}/>)}
          </div>
        )}
      </div>

      {activeLead && <LeadDetailModal lead={activeLead} onClose={()=>setActiveLead(null)}/>}
    </>
  );
}

// ─── Profile / Team / Settings ───────────────────────────────────────
function Profile({ user }) {
  return (
    <>
      <Topbar title="My profile" subtitle="How AI scores leads for you"/>
      <div className="page" style={{maxWidth:720}}>
        <div className="card" style={{padding:28, marginBottom:16}}>
          <div style={{display:'flex', alignItems:'center', gap:16, marginBottom:24}}>
            <div className="avatar avatar-lg" style={{background: user.color, width:72, height:72, fontSize:26}}>{user.initials}</div>
            <div>
              <div style={{fontSize:22, fontWeight:700, letterSpacing:'-0.01em'}}>{user.name}</div>
              <div style={{fontSize:13, color:'var(--text-muted)'}}>{user.role}</div>
            </div>
            <button className="btn btn-ghost btn-sm" style={{marginLeft:'auto'}}><Icon name="pencil" size={13}/>Edit</button>
          </div>
          <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:18}}>
            <Field label="Business size" value="Small team (2–10)"/>
            <Field label="Home region" value="Kyiv, Ukraine"/>
            <Field label="Profession / offer" value="Web design & dev for local SMB"/>
            <Field label="Target niches" value="Contractors, clinics, studios"/>
          </div>
        </div>
        <div className="card" style={{padding:20, background:'var(--surface-2)'}}>
          <div style={{display:'flex', alignItems:'center', gap:12}}>
            <Icon name="sparkles" size={16} style={{color:'var(--accent)'}}/>
            <div style={{fontSize:13, color:'var(--text-muted)'}}>Your profile personalizes every AI score and pitch. Update it anytime.</div>
          </div>
        </div>
      </div>
    </>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <div className="eyebrow" style={{marginBottom:6}}>{label}</div>
      <div style={{fontSize:14}}>{value}</div>
    </div>
  );
}

function TeamPage() {
  return (
    <>
      <Topbar title="Team" subtitle="Manage who has access"
              right={<button className="btn btn-sm"><Icon name="plus" size={14}/>Invite</button>} />
      <div className="page" style={{maxWidth:900}}>
        <div className="card" style={{padding:0, overflow:'hidden'}}>
          <table className="tbl">
            <thead><tr><th>Member</th><th>Role</th><th>Last active</th><th>Searches</th><th></th></tr></thead>
            <tbody>
              {window.MOCK_TEAM.map(m => (
                <tr key={m.id}>
                  <td><div style={{display:'flex', alignItems:'center', gap:10}}><div className="avatar" style={{background:m.color}}>{m.initials}</div><div><div style={{fontWeight:600}}>{m.name}</div><div style={{fontSize:11.5, color:'var(--text-muted)'}}>{m.name.toLowerCase()}@leadgen.app</div></div></div></td>
                  <td><span className="chip" style={{fontSize:11}}>{m.role}</span></td>
                  <td style={{color:'var(--text-muted)', fontSize:12.5}}>2 hours ago</td>
                  <td style={{fontFamily:'var(--font-mono)'}}>{Math.floor(Math.random()*20)+3}</td>
                  <td><button className="btn-icon"><Icon name="moreH" size={16}/></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function SettingsPage() {
  return (
    <>
      <Topbar title="Settings" subtitle="Workspace configuration"/>
      <div className="page" style={{maxWidth:720}}>
        <div className="card" style={{padding:24, marginBottom:14}}>
          <div className="eyebrow" style={{marginBottom:14}}>Workspace</div>
          <Field label="Workspace name" value="Acme Digital Agency"/>
          <div style={{marginTop:16}}><Field label="Plan" value="Team · 150 searches / mo"/></div>
        </div>
        <div className="card" style={{padding:24, marginBottom:14}}>
          <div className="eyebrow" style={{marginBottom:14}}>Integrations</div>
          <div style={{display:'flex', flexDirection:'column', gap:10}}>
            {[{n:'Google Places', s:'connected'},{n:'Anthropic (Claude)', s:'connected'},{n:'Telegram bot', s:'connected'},{n:'Email delivery', s:'not configured'}].map((i,k)=>(
              <div key={k} style={{display:'flex', alignItems:'center', justifyContent:'space-between', padding:'10px 0', borderBottom: k<3?'1px solid var(--border)':'none'}}>
                <div style={{fontSize:14}}>{i.n}</div>
                <div style={{display:'flex', alignItems:'center', gap:8}}>
                  <span className="status-dot" style={{background: i.s==='connected'?'var(--hot)':'var(--text-dim)'}}></span>
                  <span style={{fontSize:12, color:'var(--text-muted)'}}>{i.s}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

Object.assign(window, { SessionDetail, SessionsList, LeadsCRM, Profile, TeamPage, SettingsPage, LeadCard, LeadDetailModal });
