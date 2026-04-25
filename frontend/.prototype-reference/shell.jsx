// shell.jsx — top-level layout, router, auth, state

const { useCallback } = React;

// ─── Auth (fake localStorage) ───────────────────────────────────────────
const AUTH_KEY = 'leadgen.auth.v1';
const getSavedAuth = () => {
  try { return JSON.parse(localStorage.getItem(AUTH_KEY) || 'null'); } catch { return null; }
};
const saveAuth = (u) => localStorage.setItem(AUTH_KEY, JSON.stringify(u));
const clearAuth = () => localStorage.removeItem(AUTH_KEY);

// ─── Route (hash-based) ────────────────────────────────────────────────
const useRoute = () => {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || '/');
  useEffect(() => {
    const h = () => setRoute(window.location.hash.slice(1) || '/');
    window.addEventListener('hashchange', h);
    return () => window.removeEventListener('hashchange', h);
  }, []);
  const navigate = (path) => { window.location.hash = path; };
  return [route, navigate];
};

// ─── Sidebar ────────────────────────────────────────────────────────────
function Sidebar({ route, navigate, user, onLogout, tweaks }) {
  const nav = [
    { section: 'Workspace' },
    { key: '/app', label: 'Dashboard', icon: 'home' },
    { key: '/app/search', label: 'New search', icon: 'sparkles' },
    { key: '/app/sessions', label: 'Sessions', icon: 'folder' },
    { key: '/app/leads', label: 'All leads', icon: 'list' },
    { section: 'Team' },
    { key: '/app/team', label: 'Team', icon: 'users' },
    { key: '/app/profile', label: 'My profile', icon: 'user' },
    { key: '/app/settings', label: 'Settings', icon: 'settings' },
  ];
  return (
    <aside className="sidebar">
      <div style={{display:'flex', alignItems:'center', gap:10, padding:'4px 12px 20px'}}>
        <div style={{
          width:28, height:28, borderRadius:8,
          background:'linear-gradient(135deg, var(--accent), #6a7bff)',
          display:'grid', placeItems:'center', color:'white', fontSize:13, fontWeight:700,
        }}>L</div>
        <div style={{fontWeight:700, fontSize:15, letterSpacing:'-0.01em'}}>Leadgen</div>
        <div className="chip" style={{marginLeft:'auto', fontSize:10, padding:'2px 7px'}}>beta</div>
      </div>

      {nav.map((item, i) => item.section ? (
        <div key={i} className="nav-section">{item.section}</div>
      ) : (
        <div key={item.key}
             className={'nav-item' + (route === item.key ? ' active' : '')}
             onClick={() => navigate(item.key)}>
          <Icon name={item.icon} size={17} />
          <span>{item.label}</span>
        </div>
      ))}

      <div style={{marginTop:'auto', paddingTop:20}}>
        <div className="card" style={{padding:14, background:'var(--surface-2)', border:'1px solid var(--border)'}}>
          <div style={{display:'flex', alignItems:'center', gap:10}}>
            <div className="avatar" style={{background: user.color}}>{user.initials}</div>
            <div style={{minWidth:0, flex:1}}>
              <div style={{fontSize:13, fontWeight:600, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>{user.name}</div>
              <div style={{fontSize:11, color:'var(--text-muted)'}}>{user.role}</div>
            </div>
            <button className="btn-icon" onClick={onLogout} title="Sign out"><Icon name="logout" size={15}/></button>
          </div>
        </div>
      </div>
    </aside>
  );
}

// ─── Topbar ─────────────────────────────────────────────────────────────
function Topbar({ title, subtitle, right, crumbs }) {
  return (
    <div className="topbar">
      <div style={{display:'flex', alignItems:'center', gap:14, minWidth:0}}>
        {crumbs && (
          <div style={{display:'flex', alignItems:'center', gap:6, fontSize:13, color:'var(--text-muted)'}}>
            {crumbs.map((c, i) => (
              <React.Fragment key={i}>
                {i > 0 && <Icon name="chevronRight" size={14} />}
                {c.href
                  ? <a href={'#' + c.href} style={{color:'inherit'}}>{c.label}</a>
                  : <span style={{color:'var(--text)'}}>{c.label}</span>}
              </React.Fragment>
            ))}
          </div>
        )}
        {!crumbs && (
          <div>
            <div style={{fontSize:16, fontWeight:600, letterSpacing:'-0.01em'}}>{title}</div>
            {subtitle && <div style={{fontSize:12.5, color:'var(--text-muted)', marginTop:2}}>{subtitle}</div>}
          </div>
        )}
      </div>
      <div style={{display:'flex', alignItems:'center', gap:10}}>
        {right}
        <button className="btn-icon" title="Notifications"><Icon name="bell" size={17}/></button>
        <div className="kbd">⌘ K</div>
      </div>
    </div>
  );
}

// AppShell — wraps a page with the sidebar + main scroll area
function AppShell({ user, navigate, route, children }) {
  const handleLogout = () => { try { clearAuth(); } catch(e){} navigate('/landing'); };
  return (
    <div className="app-layout">
      <Sidebar user={user} route={route} navigate={navigate} onLogout={handleLogout} />
      <main className="main-area">{children}</main>
    </div>
  );
}

window.useRoute = useRoute;
window.getSavedAuth = getSavedAuth;
window.saveAuth = saveAuth;
window.clearAuth = clearAuth;
window.Sidebar = Sidebar;
window.Topbar = Topbar;
window.AppShell = AppShell;

