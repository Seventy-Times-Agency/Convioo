// auth.jsx — login and register screens

function AuthShell({ title, children }) {
  return (
    <div style={{minHeight:'100vh', display:'grid', gridTemplateColumns:'1fr 1fr', background:'var(--bg)'}}>
      {/* left — form */}
      <div style={{display:'flex', flexDirection:'column', padding:'40px 56px'}}>
        <div style={{display:'flex', alignItems:'center', gap:10}}>
          <div style={{
            width:28, height:28, borderRadius:8,
            background:'linear-gradient(135deg, var(--accent), #6a7bff)',
            display:'grid', placeItems:'center', color:'white', fontSize:13, fontWeight:700,
          }}>L</div>
          <a href="#/" style={{fontWeight:700, fontSize:15}}>Leadgen</a>
        </div>
        <div style={{flex:1, display:'flex', alignItems:'center'}}>
          <div style={{width:'100%', maxWidth:400}}>
            <h1 style={{fontSize:44, fontWeight:700, letterSpacing:'-0.03em', lineHeight:1.02, margin:'0 0 12px'}}>{title}</h1>
            {children}
          </div>
        </div>
        <div style={{fontSize:12, color:'var(--text-dim)'}}>© 2026 Leadgen · Team access only</div>
      </div>

      {/* right — decorative */}
      <div style={{position:'relative', overflow:'hidden', background:'var(--surface)', borderLeft:'1px solid var(--border)'}}>
        <div className="mesh-bg"><div className="blob3"></div></div>
        <div style={{position:'absolute', inset:0, padding:56, display:'flex', flexDirection:'column', justifyContent:'flex-end'}}>
          <div className="eyebrow" style={{marginBottom:16}}>Inside</div>
          <div style={{fontSize:30, fontWeight:600, letterSpacing:'-0.02em', lineHeight:1.15, color:'var(--text)', maxWidth:380, textWrap:'balance'}}>
            50 AI-scored prospects. Every search. Personalized to what <span style={{fontStyle:'italic', color:'var(--text-muted)'}}>you</span> sell.
          </div>
          <div style={{display:'flex', gap:14, marginTop:32, color:'var(--text-muted)', fontSize:13}}>
            <span>Google Places</span> · <span>Claude Haiku</span> · <span>Live enrichment</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function LoginScreen({ onAuth, navigate }) {
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState('');
  const submit = (e) => {
    e.preventDefault();
    if (!name.trim() || !password.trim()) { setErr('Enter name and password'); return; }
    // Match against team
    const member = window.MOCK_TEAM.find(m => m.name.toLowerCase() === name.trim().toLowerCase());
    onAuth(member || { ...window.MOCK_TEAM[0], name: name.trim(), initials: name.trim()[0].toUpperCase() });
  };
  return (
    <AuthShell title="Welcome back.">
      <div style={{color:'var(--text-muted)', marginBottom:28, fontSize:15}}>Sign in to continue to your workspace.</div>
      <form onSubmit={submit} style={{display:'flex', flexDirection:'column', gap:14}}>
        <div>
          <label style={{fontSize:12, fontWeight:600, color:'var(--text-muted)', marginBottom:6, display:'block'}}>Name</label>
          <input className="input" value={name} onChange={e=>setName(e.target.value)} placeholder="Denys" autoFocus />
        </div>
        <div>
          <label style={{fontSize:12, fontWeight:600, color:'var(--text-muted)', marginBottom:6, display:'block'}}>Password</label>
          <input className="input" type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="••••••••" />
        </div>
        {err && <div style={{fontSize:13, color:'var(--cold)'}}>{err}</div>}
        <button className="btn btn-lg" type="submit" style={{marginTop:10, justifyContent:'center'}}>Sign in <Icon name="arrow" size={15}/></button>
      </form>
      <div style={{marginTop:24, fontSize:13.5, color:'var(--text-muted)'}}>
        New teammate? <a onClick={()=>navigate('/register')} style={{color:'var(--accent)', cursor:'pointer', fontWeight:500}}>Create account</a>
      </div>
      <div style={{marginTop:32, padding:12, background:'var(--surface-2)', border:'1px solid var(--border)', borderRadius:10, fontSize:12, color:'var(--text-muted)'}}>
        <b>Demo tip:</b> type any name + any password to enter. Try Denys, Alina, Max, or Kira.
      </div>
    </AuthShell>
  );
}

function RegisterScreen({ onAuth, navigate }) {
  const [name, setName] = useState('');
  const [role, setRole] = useState('SDR');
  const [password, setPassword] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const submit = (e) => {
    e.preventDefault();
    if (!name.trim() || !password.trim()) return;
    const colors = ['#3D5AFE','#F59E0B','#16A34A','#EC4899','#8B5CF6','#06B6D4'];
    onAuth({
      id: 'u-new', name: name.trim(), role,
      initials: name.trim().slice(0,1).toUpperCase(),
      color: colors[Math.floor(Math.random() * colors.length)],
    });
  };
  return (
    <AuthShell title="Join your team.">
      <div style={{color:'var(--text-muted)', marginBottom:28, fontSize:15}}>Your admin invited you. Create a lightweight account.</div>
      <form onSubmit={submit} style={{display:'flex', flexDirection:'column', gap:14}}>
        <div>
          <label style={{fontSize:12, fontWeight:600, color:'var(--text-muted)', marginBottom:6, display:'block'}}>Your name</label>
          <input className="input" value={name} onChange={e=>setName(e.target.value)} placeholder="Alex" autoFocus />
        </div>
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:12}}>
          <div>
            <label style={{fontSize:12, fontWeight:600, color:'var(--text-muted)', marginBottom:6, display:'block'}}>Role</label>
            <select className="select" value={role} onChange={e=>setRole(e.target.value)}>
              <option>SDR</option><option>Founder</option><option>Marketing Lead</option>
              <option>Copywriter</option><option>Designer</option>
            </select>
          </div>
          <div>
            <label style={{fontSize:12, fontWeight:600, color:'var(--text-muted)', marginBottom:6, display:'block'}}>Invite code</label>
            <input className="input" value={inviteCode} onChange={e=>setInviteCode(e.target.value)} placeholder="LG-TEAM-01" />
          </div>
        </div>
        <div>
          <label style={{fontSize:12, fontWeight:600, color:'var(--text-muted)', marginBottom:6, display:'block'}}>Password</label>
          <input className="input" type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="At least 8 characters" />
        </div>
        <button className="btn btn-lg" type="submit" style={{marginTop:10, justifyContent:'center'}}>Create account <Icon name="arrow" size={15}/></button>
      </form>
      <div style={{marginTop:24, fontSize:13.5, color:'var(--text-muted)'}}>
        Already have an account? <a onClick={()=>navigate('/login')} style={{color:'var(--accent)', cursor:'pointer', fontWeight:500}}>Sign in</a>
      </div>
    </AuthShell>
  );
}

window.LoginScreen = LoginScreen;
window.RegisterScreen = RegisterScreen;
