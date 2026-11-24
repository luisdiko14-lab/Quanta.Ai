import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
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

const quickPrompts = [
  { icon: Code2, title: 'Build something', detail: 'Turn an idea into clean, working code.' },
  { icon: FileText, title: 'Understand a file', detail: 'Summarize, compare, or explore a document.' },
  { icon: Globe2, title: 'Explore a topic', detail: 'Get a clear explanation and useful next steps.' },
  { icon: WandSparkles, title: 'Create an idea', detail: 'Brainstorm something original and useful.' },
];

const starterChats = ['Designing a product roadmap', 'Python async patterns', 'Ideas for a new project'];

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
  const [streaming, setStreaming] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [error, setError] = useState('');
  const [providerState, setProviderState] = useState<'checking' | 'online' | 'offline'>('checking');
  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    window.localStorage.setItem('quanta-theme', theme);
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetch('/api/v1/models').then((response) => response.ok ? response.json() : Promise.reject()),
      fetch('/health/live').then((response) => response.ok),
    ])
      .then(([modelPayload, online]) => {
        if (!active) return;
        setModels(modelPayload.data ?? []);
        setProviderState(online ? 'online' : 'offline');
      })
      .catch(() => {
        if (active) setProviderState('offline');
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streaming]);

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
        headers: { 'Content-Type': 'application/json' },
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
          <button className="profile-row" disabled title="Account profiles are coming in the authentication milestone">
            <div className="avatar">G</div>
            <div className="profile-copy"><strong>Guest workspace</strong><span>Local preview</span></div>
            <Settings2 size={17} />
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
                  {models.map((option) => <option value={option.id} key={option.id}>{option.label}</option>)}
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
              <button className="send-button" onClick={() => void sendMessage()} disabled={!draft.trim() || streaming} aria-label="Send message">
                {streaming ? <span className="send-spinner" /> : <Send size={16} />}
              </button>
            </div>
          </div>
          <div className="disclaimer">Quanta AI can make mistakes. Verify important information.</div>
        </div>
      </main>
    </div>
  );
}

export default App;
