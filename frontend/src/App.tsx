import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import {
  ArrowUp,
  AudioLines,
  ChevronDown,
  CircleHelp,
  Code2,
  Command,
  FileText,
  Globe2,
  Image as ImageIcon,
  LayoutDashboard,
  LockKeyhole,
  LogIn,
  Menu,
  MessageSquare,
  Moon,
  MoreHorizontal,
  Paperclip,
  PanelLeftClose,
  Plus,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Sun,
  WandSparkles,
  X,
  Zap,
} from 'lucide-react';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

type ModelOption = { id: string; label: string; provider: string; access: string };
type Identity = {
  user_id?: string | null;
  username: string;
  display_name: string;
  role: string;
  plan: string;
  kind: string;
};
type AuthMode = 'login' | 'register' | 'verify' | 'forgot' | 'reset' | 'account';
type ConversationSummary = {
  id: string;
  title: string;
  model: string;
  created_at: string | null;
  updated_at: string | null;
};

const quickPrompts = [
  { icon: Code2, title: 'Build something', detail: 'Turn an idea into clean, working code.' },
  { icon: FileText, title: 'Understand a file', detail: 'Summarize, compare, or explore a document.' },
  { icon: Globe2, title: 'Explore a topic', detail: 'Get a clear explanation and useful next steps.' },
  { icon: WandSparkles, title: 'Create an idea', detail: 'Brainstorm something original and useful.' },
];

function QMark() {
  return <span className="q-mark" aria-hidden="true">Q<span /></span>;
}

function App() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => (
    window.localStorage.getItem('quanta-theme') === 'light' ? 'light' : 'dark'
  ));
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [model, setModel] = useState('auto');
  const [models, setModels] = useState<ModelOption[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationSearch, setConversationSearch] = useState('');
  const [historyVersion, setHistoryVersion] = useState(0);
  const [streaming, setStreaming] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [error, setError] = useState('');
  const [csrfToken, setCsrfToken] = useState('');
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<AuthMode>('login');
  const [authEmail, setAuthEmail] = useState('');
  const [authUsername, setAuthUsername] = useState('');
  const [authDisplayName, setAuthDisplayName] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authToken, setAuthToken] = useState('');
  const [authNotice, setAuthNotice] = useState('');
  const [authError, setAuthError] = useState('');
  const [authBusy, setAuthBusy] = useState(false);
  const [providerState, setProviderState] = useState<'checking' | 'online' | 'offline'>('checking');
  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    window.localStorage.setItem('quanta-theme', theme);
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    let active = true;
    const bootstrap = async () => {
      try {
        const csrfResponse = await fetch('/api/v1/auth/csrf', { credentials: 'include' });
        if (!csrfResponse.ok) throw new Error('Could not initialize a secure session.');
        const csrfPayload = await csrfResponse.json();
        let token = csrfPayload.csrf_token as string;

        const meResponse = await fetch('/api/v1/auth/me', { credentials: 'include' });
        if (meResponse.ok) {
          const currentIdentity = await meResponse.json() as Identity;
          if (active) setIdentity(currentIdentity);
        } else {
          const guestResponse = await fetch('/api/v1/auth/guest', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
            body: '{}',
          });
          if (!guestResponse.ok) throw new Error('Could not start a guest session.');
          const guestPayload = await guestResponse.json();
          token = guestPayload.csrf_token as string;
          if (active) {
            setIdentity({
              username: 'Guest',
              display_name: 'Guest workspace',
              role: 'guest',
              plan: 'guest',
              kind: 'guest',
            });
          }
        }

        const route = window.location.pathname;
        const urlToken = new URLSearchParams(window.location.search).get('token') ?? '';
        if (route.startsWith('/verify-email') && urlToken) {
          try {
            const verificationResponse = await fetch('/api/v1/auth/verify-email', {
              method: 'POST',
              credentials: 'include',
              headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
              body: JSON.stringify({ token: urlToken }),
            });
            const verificationPayload = await verificationResponse.json().catch(() => ({}));
            if (!verificationResponse.ok) {
              setAuthError(verificationPayload.detail ?? 'This verification link is invalid or expired.');
              setAuthMode('verify');
              setAuthToken(urlToken);
            } else {
              setAuthNotice(verificationPayload.message ?? 'Email verified. You can now sign in.');
              setAuthMode('login');
            }
          } catch {
            setAuthError('Could not verify this email link. Please try again.');
            setAuthMode('verify');
            setAuthToken(urlToken);
          }
          setAuthOpen(true);
          window.history.replaceState({}, '', '/');
        } else if (route.startsWith('/reset-password') && urlToken) {
          setAuthToken(urlToken);
          setAuthMode('reset');
          setAuthOpen(true);
          window.history.replaceState({}, '', '/');
        }

        const [modelResponse, healthResponse] = await Promise.all([
          fetch('/api/v1/models', { credentials: 'include' }),
          fetch('/health/live'),
        ]);
        if (!modelResponse.ok || !healthResponse.ok) throw new Error('The Quanta API is unavailable.');
        const modelPayload = await modelResponse.json();
        if (!active) return;
        setCsrfToken(token);
        setModels(modelPayload.data ?? []);
        setProviderState('online');
      } catch {
        if (active) setProviderState('offline');
      }
    };
    void bootstrap();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (identity?.kind !== 'user') {
      setConversations([]);
      return;
    }
    let active = true;
    fetch('/api/v1/conversations', { credentials: 'include' })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((payload) => {
        if (active) setConversations(payload.data ?? []);
      })
      .catch(() => {
        if (active) setConversations([]);
      });
    return () => { active = false; };
  }, [identity?.kind, identity?.user_id, historyVersion]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streaming]);

  const openConversation = async (conversation: ConversationSummary) => {
    if (streaming) return;
    try {
      const response = await fetch(
        `/api/v1/conversations/${conversation.id}/messages`,
        { credentials: 'include' },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail ?? 'Could not open this conversation.');
      setConversationId(conversation.id);
      setModel(conversation.model || 'auto');
      setMessages((payload.data ?? []).map((message: ChatMessage) => ({
        id: message.id,
        role: message.role,
        content: message.content,
      })));
      setError('');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not open conversation.');
    }
  };

  const filteredConversations = conversations.filter((conversation) =>
    conversation.title.toLowerCase().includes(conversationSearch.toLowerCase())
  );

  const updateAssistant = (id: string, content: string) => {
    setMessages((current) => current.map((message) => (
      message.id === id ? { ...message, content: message.content + content } : message
    )));
  };

  const sendMessage = async (text = draft) => {
    const prompt = text.trim();
    if (!prompt || streaming) return;
    setError('');
    setDraft('');
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: prompt };
    const assistantMessage: ChatMessage = { id: crypto.randomUUID(), role: 'assistant', content: '' };
    const nextMessages = [...messages, userMessage];
    setMessages([...nextMessages, assistantMessage]);
    setStreaming(true);

    try {
      const response = await fetch('/api/v1/chat/completions', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          model,
          messages: nextMessages.map(({ role, content }) => ({ role, content })),
          stream: true,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail ?? 'Quanta could not reach an AI provider.');
      }
      if (!response.body) throw new Error('Streaming is not supported by this connection.');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split('\n\n');
        buffer = frames.pop() ?? '';
        for (const frame of frames) {
          const line = frame.split('\n').find((part) => part.startsWith('data:'));
          if (!line) continue;
          const data = line.slice(5).trim();
          if (data === '[DONE]') continue;
          const chunk = JSON.parse(data);
          if (chunk.error?.message) throw new Error(chunk.error.message);
          const token = chunk.choices?.[0]?.delta?.content;
          if (token) updateAssistant(assistantMessage.id, token);
        }
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Something went wrong.';
      setError(message);
      updateAssistant(assistantMessage.id, 'I could not complete that response. Check the API configuration and try again.');
    } finally {
      setStreaming(false);
      composerRef.current?.focus();
    }
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  };

  const openAuth = (mode: AuthMode = 'login') => {
    setAuthMode(mode);
    setAuthNotice('');
    setAuthError('');
    setAuthOpen(true);
  };

  const submitAuth = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (authBusy) return;
    setAuthBusy(true);
    setAuthError('');
    setAuthNotice('');
    let endpoint = '';
    let payload: Record<string, string> = {};

    if (authMode === 'login') {
      endpoint = '/api/v1/auth/login';
      payload = { login: authEmail, password: authPassword };
    } else if (authMode === 'register') {
      endpoint = '/api/v1/auth/register';
      payload = {
        email: authEmail,
        username: authUsername,
        display_name: authDisplayName,
        password: authPassword,
      };
    } else if (authMode === 'verify') {
      endpoint = '/api/v1/auth/verify-email';
      payload = { token: authToken };
    } else if (authMode === 'forgot') {
      endpoint = '/api/v1/auth/password/forgot';
      payload = { email: authEmail };
    } else if (authMode === 'reset') {
      endpoint = '/api/v1/auth/password/reset';
      payload = { token: authToken, new_password: authPassword };
    } else {
      setAuthBusy(false);
      return;
    }

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail ?? data.message ?? 'That request could not be completed.');

      if (authMode === 'login') {
        setIdentity(data.user as Identity);
        setCsrfToken(data.csrf_token as string);
        setAuthOpen(false);
        setAuthPassword('');
        setAuthNotice('');
      } else if (authMode === 'register') {
        setAuthNotice(data.message ?? 'Account created. Check your email to verify it.');
        if (data.development_verification_token) {
          setAuthToken(data.development_verification_token);
          setAuthMode('verify');
        } else {
          setAuthMode('login');
        }
        setAuthPassword('');
      } else if (authMode === 'verify') {
        setAuthNotice(data.message ?? 'Email verified. You can now sign in.');
        setAuthMode('login');
        setAuthToken('');
      } else if (authMode === 'forgot') {
        if (data.development_reset_token) {
          setAuthToken(data.development_reset_token);
          setAuthMode('reset');
          setAuthNotice('Development reset token created for this local environment.');
        } else {
          setAuthNotice(data.message ?? 'Check your email for reset instructions.');
          setAuthMode('login');
        }
      } else if (authMode === 'reset') {
        setAuthNotice(data.message ?? 'Password updated. Please sign in.');
        setAuthMode('login');
        setAuthToken('');
        setAuthPassword('');
      }
    } catch (caught) {
      setAuthError(caught instanceof Error ? caught.message : 'Something went wrong.');
    } finally {
      setAuthBusy(false);
    }
  };

  const logout = async () => {
    try {
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-CSRF-Token': csrfToken },
      });
      const csrfResponse = await fetch('/api/v1/auth/csrf', { credentials: 'include' });
      const csrfPayload = await csrfResponse.json();
      const token = csrfPayload.csrf_token as string;
      const guestResponse = await fetch('/api/v1/auth/guest', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
        body: '{}',
      });
      if (!guestResponse.ok) throw new Error('Could not start a guest session.');
      const guestPayload = await guestResponse.json();
      setCsrfToken(guestPayload.csrf_token as string);
      setIdentity({
        username: 'Guest',
        display_name: 'Guest workspace',
        role: 'guest',
        plan: 'guest',
        kind: 'guest',
      });
      setAuthOpen(false);
      setMessages([]);
    } catch {
      setAuthError('Could not sign out safely. Please refresh the page.');
    }
  };

  return (
    <div className="app-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <aside className={sidebarOpen ? 'sidebar' : 'sidebar sidebar-hidden'}>
        <div className="brand-row">
          <div className="brand-lockup"><QMark /><span>quanta<span className="brand-ai">AI</span></span></div>
          <button className="icon-button subtle mobile-only" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar"><X size={18} /></button>
          <button className="icon-button subtle desktop-only" onClick={() => setSidebarOpen(false)} aria-label="Collapse sidebar"><PanelLeftClose size={18} /></button>
        </div>

        <button className="new-chat-button" onClick={() => { setMessages([]); setDraft(''); setError(''); }}>
          <Plus size={17} /> <span>New conversation</span> <kbd>⌘ K</kbd>
        </button>

        <label className="sidebar-search">
          <Search size={15} />
          <input aria-label="Search conversations" placeholder="Search conversations" />
          <kbd>/</kbd>
        </label>

        <div className="sidebar-section">
          <div className="section-label">Workspace</div>
          <button className="nav-item active"><MessageSquare size={16} /><span>AI Chat</span><span className="nav-dot" /></button>
          <button className="nav-item" disabled title="Model explorer is planned for a later milestone"><LayoutDashboard size={16} /><span>Explore models</span></button>
          <button className="nav-item" disabled title="Image tools are planned for a later milestone"><ImageIcon size={16} /><span>Image studio</span><span className="soon-label">Soon</span></button>
          <button className="nav-item" disabled title="Document tools are planned for a later milestone"><FileText size={16} /><span>Documents</span><span className="soon-label">Soon</span></button>
        </div>

        <div className="sidebar-section recent-section">
          <div className="section-heading"><span className="section-label">Recent</span><button className="tiny-icon" aria-label="More conversations" disabled><MoreHorizontal size={16} /></button></div>
          {starterChats.map((chat) => (
            <button className="recent-chat" key={chat} onClick={() => { setMessages([]); setDraft('Help me continue: ' + chat); composerRef.current?.focus(); }}>
              <MessageSquare size={14} /><span>{chat}</span>
            </button>
          ))}
        </div>

        <div className="sidebar-bottom">
          <div className="upgrade-card">
            <div className="upgrade-icon"><Zap size={16} /></div>
            <div><strong>More room to think</strong><span>Explore Quanta plans</span></div>
            <ArrowUp size={15} />
          </div>
          <button className="profile-row" onClick={() => openAuth(identity?.kind === 'user' ? 'account' : 'login')}>
            <div className="avatar">{(identity?.display_name || 'G').slice(0, 1).toUpperCase()}</div>
            <div className="profile-copy">
              <strong>{identity?.display_name || 'Guest workspace'}</strong>
              <span>{identity?.plan ? identity.plan.replaceAll('_', ' ') : 'Guest session'}</span>
            </div>
            {identity?.kind === 'user' ? <Settings2 size={17} /> : <LogIn size={17} />}
          </button>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="topbar-left">
            {!sidebarOpen && <button className="icon-button" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar"><Menu size={19} /></button>}
            <div className="workspace-name"><span>Workspace</span><span className="crumb-divider">/</span><strong>AI Chat</strong></div>
          </div>
          <div className="topbar-actions">
            <div className={'connection-pill ' + providerState}><span className="connection-dot" />{providerState === 'online' ? 'API connected' : providerState === 'checking' ? 'Connecting' : 'API offline'}</div>
            <button className="icon-button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label="Toggle theme">{theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}</button>
            <button className="help-button" disabled><CircleHelp size={17} /><span>Help</span></button>
          </div>
        </header>

        <div className="chat-scroll" ref={scrollRef}>
          {messages.length === 0 ? (
            <section className="welcome-view">
              <div className="welcome-orb"><div className="orb-ring ring-one" /><div className="orb-ring ring-two" /><QMark /></div>
              <div className="eyebrow"><Sparkles size={13} /> YOUR INTELLIGENCE WORKSPACE</div>
              <h1>What will we <span>think up</span> today?</h1>
              <p className="welcome-copy">A little curiosity can go a long way. Bring a question, a challenge, or a half-formed idea.</p>
              <div className="prompt-grid">
                {quickPrompts.map(({ icon: Icon, title, detail }) => (
                  <button className="prompt-card" key={title} onClick={() => { setDraft(title + ': '); composerRef.current?.focus(); }}>
                    <span className="prompt-icon"><Icon size={18} /></span>
                    <span className="prompt-title">{title}</span>
                    <span className="prompt-detail">{detail}</span>
                    <ArrowUp size={15} className="prompt-arrow" />
                  </button>
                ))}
              </div>
              <div className="welcome-foot"><ShieldCheck size={14} /> Thoughtful by design. Your provider keys stay on the server.</div>
            </section>
          ) : (
            <section className="messages-view">
              <div className="conversation-heading"><span className="conversation-kicker">CONVERSATION</span><button className="icon-button subtle" disabled><MoreHorizontal size={18} /></button></div>
              {messages.map((message) => (
                <article className={'message-row ' + message.role} key={message.id}>
                  <div className={message.role === 'assistant' ? 'message-avatar assistant-avatar' : 'message-avatar user-avatar'}>
                    {message.role === 'assistant' ? <QMark /> : 'G'}
                  </div>
                  <div className="message-content">
                    <div className="message-meta"><strong>{message.role === 'assistant' ? 'Quanta' : 'You'}</strong>{message.role === 'assistant' && <span className="model-tag"><Sparkles size={11} /> AI</span>}</div>
                    <div className="message-text">{message.content || (streaming && message.role === 'assistant' ? <span className="thinking-dots"><i /><i /><i /></span> : '')}</div>
                  </div>
                </article>
              ))}
            </section>
          )}
        </div>

        <div className="composer-area">
          {error && <div className="inline-error"><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error"><X size={14} /></button></div>}
          <div className="composer-wrap">
            <div className="composer-topline">
              <div className="model-select-wrap">
                <Sparkles size={14} />
                <select value={model} onChange={(event) => setModel(event.target.value)} aria-label="Select AI model">
                  <option value="auto">Auto · Best available</option>
                  {models.map((option) => <option value={option.id} key={option.id} disabled={option.access === 'premium'}>{option.label}{option.access === 'premium' ? ' · Premium' : ''}</option>)}
                </select>
                <ChevronDown size={13} />
              </div>
              <span className="composer-context">Provider routing <span className="context-live">●</span></span>
            </div>
            <textarea
              ref={composerRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="Message Quanta AI..."
              rows={2}
              aria-label="Message Quanta AI"
            />
            <div className="composer-toolbar">
              <div className="composer-tools">
                <button className="tool-button" disabled aria-label="Attach file" title="File uploads are coming in a later milestone"><Paperclip size={17} /><span>Attach</span></button>
                <button className="tool-button" disabled aria-label="Voice input" title="Voice input is planned"><AudioLines size={17} /></button>
                <span className="tool-divider" />
                <span className="composer-hint"><Command size={12} /> + Enter to send</span>
              </div>
              <button className="send-button" onClick={() => void sendMessage()} disabled={!draft.trim() || streaming || !csrfToken} aria-label="Send message">
                {streaming ? <span className="send-spinner" /> : <Send size={16} />}
              </button>
            </div>
          </div>
          <div className="disclaimer">Quanta AI can make mistakes. Verify important information.</div>
        </div>
      </main>

      {authOpen && (
        <div className="auth-overlay" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setAuthOpen(false);
        }}>
          <section className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title">
            <button className="auth-close" onClick={() => setAuthOpen(false)} aria-label="Close account dialog"><X size={18} /></button>
            <div className="auth-brand"><QMark /></div>
            {authMode === 'account' ? (
              <>
                <div className="auth-eyebrow">YOUR ACCOUNT</div>
                <h2 id="auth-title">{identity?.display_name || identity?.username}</h2>
                <p className="auth-subtitle">Signed in to Quanta AI · {identity?.plan?.replaceAll('_', ' ')}</p>
                <div className="account-summary">
                  <span>Username</span><strong>{identity?.username}</strong>
                  <span>Membership</span><strong>{identity?.plan?.replaceAll('_', ' ')}</strong>
                  <span>Role</span><strong>{identity?.role}</strong>
                </div>
                <button className="auth-submit" onClick={() => void logout()}>Sign out</button>
              </>
            ) : (
              <>
                <div className="auth-eyebrow">QUANTA AI ACCOUNT</div>
                <h2 id="auth-title">
                  {authMode === 'login' ? 'Welcome back' :
                   authMode === 'register' ? 'Create your account' :
                   authMode === 'verify' ? 'Verify your email' :
                   authMode === 'forgot' ? 'Reset your password' : 'Choose a new password'}
                </h2>
                <p className="auth-subtitle">
                  {authMode === 'login' ? 'Sign in to keep your AI workspace connected.' :
                   authMode === 'register' ? 'Create an account to start building your workspace.' :
                   authMode === 'verify' ? 'Enter the verification token from your email.' :
                   authMode === 'forgot' ? 'We will send a secure reset link if the account exists.' :
                   'Use a new password with at least 12 characters.'}
                </p>
                {authNotice && <div className="auth-notice">{authNotice}</div>}
                {authError && <div className="auth-error">{authError}</div>}
                <form className="auth-form" onSubmit={(event) => void submitAuth(event)}>
                  {authMode === 'login' && (
                    <>
                      <label>Email or username<input value={authEmail} onChange={(event) => setAuthEmail(event.target.value)} autoComplete="username" required /></label>
                      <label>Password<input type="password" value={authPassword} onChange={(event) => setAuthPassword(event.target.value)} autoComplete="current-password" required /></label>
                    </>
                  )}
                  {authMode === 'register' && (
                    <>
                      <label>Display name<input value={authDisplayName} onChange={(event) => setAuthDisplayName(event.target.value)} autoComplete="name" maxLength={80} /></label>
                      <label>Username<input value={authUsername} onChange={(event) => setAuthUsername(event.target.value)} autoComplete="username" minLength={3} maxLength={32} pattern="[A-Za-z0-9_]+" required /></label>
                      <label>Email<input type="email" value={authEmail} onChange={(event) => setAuthEmail(event.target.value)} autoComplete="email" required /></label>
                      <label>Password<input type="password" value={authPassword} onChange={(event) => setAuthPassword(event.target.value)} autoComplete="new-password" minLength={12} maxLength={128} required /></label>
                    </>
                  )}
                  {authMode === 'verify' && (
                    <label>Verification token<input value={authToken} onChange={(event) => setAuthToken(event.target.value)} autoComplete="one-time-code" required /></label>
                  )}
                  {authMode === 'forgot' && (
                    <label>Email address<input type="email" value={authEmail} onChange={(event) => setAuthEmail(event.target.value)} autoComplete="email" required /></label>
                  )}
                  {authMode === 'reset' && (
                    <>
                      <label>Reset token<input value={authToken} onChange={(event) => setAuthToken(event.target.value)} required /></label>
                      <label>New password<input type="password" value={authPassword} onChange={(event) => setAuthPassword(event.target.value)} autoComplete="new-password" minLength={12} maxLength={128} required /></label>
                    </>
                  )}
                  <button className="auth-submit" type="submit" disabled={authBusy}>
                    {authBusy ? 'Please wait…' :
                     authMode === 'login' ? 'Sign in' :
                     authMode === 'register' ? 'Create account' :
                     authMode === 'verify' ? 'Verify email' :
                     authMode === 'forgot' ? 'Send reset link' : 'Update password'}
                  </button>
                </form>
                <div className="auth-links">
                  {authMode === 'login' && <>
                    <button onClick={() => { setAuthMode('register'); setAuthError(''); setAuthNotice(''); }}>Create account</button>
                    <button onClick={() => { setAuthMode('forgot'); setAuthError(''); setAuthNotice(''); }}>Forgot password?</button>
                  </>}
                  {authMode === 'register' && <button onClick={() => { setAuthMode('login'); setAuthError(''); setAuthNotice(''); }}>Already have an account? Sign in</button>}
                  {authMode === 'forgot' && <button onClick={() => { setAuthMode('login'); setAuthError(''); setAuthNotice(''); }}>Back to sign in</button>}
                  {(authMode === 'verify' || authMode === 'reset') && <button onClick={() => { setAuthMode('login'); setAuthError(''); setAuthNotice(''); }}>Back to sign in</button>}
                </div>
              </>
            )}
            <div className="auth-privacy"><LockKeyhole size={13} /> Protected session · Private by design</div>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
