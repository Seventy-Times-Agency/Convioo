// dashboard.jsx — main landing after login

function Dashboard({ user, navigate }) {
  const sessions = window.MOCK_SESSIONS;
  const running = sessions.filter(s => s.status === 'running');
  const totalLeads = sessions.filter(s => s.status === 'done').reduce((a, s) => a + s.leadsTotal, 0);
  const hot = sessions.filter(s => s.status === 'done').reduce((a, s) => a + s.hot, 0);

  return (
    <>
      <Topbar title={`Good ${new Date().getHours() < 12 ? 'morning' : 'afternoon'}, ${user.name}`}
              subtitle="Here's what's happening in your workspace."
              right={<button className="btn" onClick={()=>navigate('/app/search')}><Icon name="plus" size={15}/>New search</button>} />
      <div className="page">
        {/* hero stat strip */}
        <div style={{position:'relative', padding:'32px 28px', borderRadius:16, background:'var(--surface)', border:'1px solid var(--border)', overflow:'hidden', marginBottom:24}}>
          <div className="mesh-bg" style={{opacity:0.4}}></div>
          <div style={{position:'relative', display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:20}}>
            {[
              {n: sessions.length, l:'Sessions run', sub: `${running.length} active now`},
              {n: totalLeads, l:'Leads analyzed', sub:'across all sessions'},
              {n: hot, l:'Hot leads', sub:'ready for outreach', color:'var(--hot)'},
              {n: '87%', l:'Contact accuracy', sub:'verified this week', color:'var(--accent)'},
            ].map((s, i) => (
              <div key={i}>
                <div style={{fontSize:44, fontWeight:700, letterSpacing:'-0.03em', color: s.color || 'var(--text)'}}>{s.n}</div>
                <div className="eyebrow" style={{marginTop:4}}>{s.l}</div>
                <div style={{fontSize:12.5, color:'var(--text-muted)', marginTop:4}}>{s.sub}</div>
              </div>
            ))}
          </div>
        </div>

        {/* active + recent */}
        <div style={{display:'grid', gridTemplateColumns:'1.6fr 1fr', gap:20, marginBottom:24}}>
          <div>
            <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:14}}>
              <div>
                <div className="eyebrow">Recent sessions</div>
                <div style={{fontSize:22, fontWeight:600, letterSpacing:'-0.01em', marginTop:4}}>Your searches</div>
              </div>
              <a onClick={()=>navigate('/app/sessions')} style={{fontSize:13, color:'var(--accent)', cursor:'pointer'}}>View all →</a>
            </div>
            <div style={{display:'flex', flexDirection:'column', gap:10}}>
              {sessions.slice(0,4).map(s => <SessionRow key={s.id} session={s} navigate={navigate} />)}
            </div>
          </div>

          <div>
            <div style={{marginBottom:14}}>
              <div className="eyebrow">Start now</div>
              <div style={{fontSize:22, fontWeight:600, letterSpacing:'-0.01em', marginTop:4}}>Quick actions</div>
            </div>
            <div className="card card-hover" onClick={()=>navigate('/app/search')} style={{cursor:'pointer', position:'relative', overflow:'hidden', background:'linear-gradient(135deg, var(--surface), var(--surface-2))'}}>
              <Icon name="sparkles" size={22} style={{color:'var(--accent)'}} />
              <div style={{fontSize:16, fontWeight:600, marginTop:12, marginBottom:6}}>Launch a new search</div>
              <div style={{fontSize:13, color:'var(--text-muted)', lineHeight:1.5}}>Describe your target niche and region. Lumen will handle the rest.</div>
            </div>
            <div className="card card-hover" onClick={()=>navigate('/app/leads')} style={{cursor:'pointer', marginTop:10}}>
              <Icon name="list" size={22} style={{color:'var(--text-muted)'}} />
              <div style={{fontSize:16, fontWeight:600, marginTop:12, marginBottom:6}}>Open the lead base</div>
              <div style={{fontSize:13, color:'var(--text-muted)', lineHeight:1.5}}>Search, filter and organize every lead you've collected.</div>
            </div>
            <div className="card" style={{marginTop:10, background:'var(--surface-2)'}}>
              <div style={{display:'flex', alignItems:'center', gap:10, marginBottom:10}}>
                <Icon name="users" size={16} style={{color:'var(--text-muted)'}} />
                <div className="eyebrow" style={{fontSize:10}}>Team activity</div>
              </div>
              <div style={{display:'flex', flexDirection:'column', gap:10}}>
                <ActivityLine who="Alina" action="contacted" what="Hudson Valley Roofers" when="2h" />
                <ActivityLine who="Denys" action="replied" what="Apex Urban Roofing" when="30m" />
                <ActivityLine who="Max" action="created" what="Interior designers · Berlin" when="yesterday" />
              </div>
            </div>
          </div>
        </div>

        {/* hot leads */}
        <div>
          <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:14}}>
            <div>
              <div className="eyebrow">Hot this week</div>
              <div style={{fontSize:22, fontWeight:600, letterSpacing:'-0.01em', marginTop:4}}>Top-scoring leads</div>
            </div>
            <a onClick={()=>navigate('/app/leads')} style={{fontSize:13, color:'var(--accent)', cursor:'pointer'}}>Open CRM →</a>
          </div>
          <div style={{display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:14}}>
            {window.MOCK_LEADS.filter(l => l.temp === 'hot').slice(0, 3).map(l => (
              <LeadMiniCard key={l.id} lead={l} navigate={navigate}/>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

function SessionRow({ session, navigate }) {
  const isRunning = session.status === 'running';
  return (
    <div className="card card-hover" style={{cursor:'pointer', padding:'16px 20px'}} onClick={()=>navigate('/app/session/' + session.id)}>
      <div style={{display:'grid', gridTemplateColumns:'1fr auto auto auto', gap:20, alignItems:'center'}}>
        <div>
          <div style={{display:'flex', alignItems:'center', gap:10, marginBottom:4}}>
            <span className={'status-dot ' + (isRunning ? 'live' : 'hot')}></span>
            <div style={{fontSize:15, fontWeight:600}}>{session.niche}</div>
            <span className="chip" style={{fontSize:11}}><Icon name="mapPin" size={11}/>{session.region}</span>
          </div>
          <div style={{fontSize:12, color:'var(--text-muted)'}}>
            {isRunning
              ? <>Running — {session.progress}% complete</>
              : <>{session.leadsTotal} leads · {session.hot} hot · {session.warm} warm</>}
          </div>
          {isRunning && (
            <div style={{height:3, background:'var(--surface-3)', borderRadius:3, marginTop:8, overflow:'hidden'}}>
              <div style={{width: session.progress + '%', height:'100%', background:'var(--accent)', transition:'width .6s'}}></div>
            </div>
          )}
        </div>
        {!isRunning && (
          <>
            <div style={{textAlign:'right'}}>
              <div style={{fontFamily:'var(--font-mono)', fontSize:18, fontWeight:700, color:'var(--hot)'}}>{session.hot}</div>
              <div style={{fontSize:10, color:'var(--text-dim)', textTransform:'uppercase', letterSpacing:'0.12em'}}>hot</div>
            </div>
            <div style={{textAlign:'right'}}>
              <div style={{fontFamily:'var(--font-mono)', fontSize:18, fontWeight:700, color:'#B45309'}}>{session.warm}</div>
              <div style={{fontSize:10, color:'var(--text-dim)', textTransform:'uppercase', letterSpacing:'0.12em'}}>warm</div>
            </div>
          </>
        )}
        <Icon name="chevronRight" size={16} style={{color:'var(--text-dim)'}}/>
      </div>
    </div>
  );
}

function ActivityLine({ who, action, what, when }) {
  const u = window.MOCK_TEAM.find(m => m.name === who) || window.MOCK_TEAM[0];
  return (
    <div style={{display:'flex', alignItems:'center', gap:10, fontSize:12.5}}>
      <div className="avatar avatar-sm" style={{background: u.color}}>{u.initials}</div>
      <div style={{flex:1, color:'var(--text-muted)'}}>
        <span style={{color:'var(--text)', fontWeight:500}}>{who}</span> {action}{' '}
        <span style={{color:'var(--text)'}}>{what}</span>
      </div>
      <div style={{fontSize:11, color:'var(--text-dim)'}}>{when}</div>
    </div>
  );
}

function LeadMiniCard({ lead, navigate }) {
  return (
    <div className="card card-hover" style={{cursor:'pointer'}} onClick={()=>navigate('/app/session/' + lead.sessionId)}>
      <div style={{display:'flex', alignItems:'flex-start', justifyContent:'space-between', marginBottom:10}}>
        <div className={'chip chip-' + lead.temp}><span className={'status-dot ' + lead.temp}></span>{lead.temp}</div>
        <div style={{fontFamily:'var(--font-mono)', fontSize:22, fontWeight:700, color:'var(--hot)'}}>{lead.score}</div>
      </div>
      <div style={{fontSize:15, fontWeight:600, letterSpacing:'-0.005em', marginBottom:4}}>{lead.name}</div>
      <div style={{fontSize:12, color:'var(--text-muted)', marginBottom:12}}>{lead.address}</div>
      <div style={{fontSize:13, color:'var(--text-muted)', lineHeight:1.5, display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical', overflow:'hidden'}}>{lead.summary}</div>
    </div>
  );
}

window.Dashboard = Dashboard;
window.LeadMiniCard = LeadMiniCard;
window.SessionRow = SessionRow;
