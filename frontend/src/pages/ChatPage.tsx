import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, Bot, BrainCircuit, ChevronDown, ChevronRight, CircleStop, FileSearch, GitBranch, LoaderCircle, Plus, Route, Sparkles, Wrench } from "lucide-react";
import { useSSE, type SSEMessage } from "../hooks/useSSE";
import { api, type SkillInfo } from "../lib/api";
import { usePreferences } from "../hooks/usePreferences";

const MAX_INPUT_LENGTH = 10_000;
const suggestedPrompts = [
  { title: "审阅行业文档", text: "请审阅一份矿山安全生产方案，并依据知识库指出存在的问题。", icon: FileSearch, tone: "blue" },
  { title: "构建知识图谱", text: "请从一份文档中抽取实体和关系，并生成知识图谱。", icon: GitBranch, tone: "violet" },
  { title: "分析并执行任务", text: "请分析这个任务，并选择最合适的 Agent 处理。", icon: Sparkles, tone: "amber" },
];

type Activity = { kind: "route" | "tool" | "status"; label: string; detail?: string };
type ChatTurn = { id: string; role: "user" | "assistant"; content: string; reasoning: string; activities: Activity[]; pending?: boolean; stopped?: boolean; error?: string };

function createTurn(role: ChatTurn["role"], content = ""): ChatTurn {
  return { id: crypto.randomUUID(), role, content, reasoning: "", activities: [] };
}

export default function ChatPage() {
  const [input, setInput] = useState("");
  const { preferences, profileId } = usePreferences();
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [selectedAgent, setSelectedAgent] = useState("");
  const [selectedSkill, setSelectedSkill] = useState("");
  const [thinking, setThinking] = useState(false);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [skillsError, setSkillsError] = useState(false);
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const { messages, isStreaming, send, stop } = useSSE();
  const processedEvents = useRef(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    api.getSkills().then((data) => setSkills(data.skills || [])).catch(() => setSkillsError(true));
  }, []);

  useEffect(() => {
    if (messages.length < processedEvents.current) processedEvents.current = 0;
    const newEvents = messages.slice(processedEvents.current);
    processedEvents.current = messages.length;
    if (newEvents.length === 0) return;
    setTurns((previous) => previous.map((turn, index) => index === previous.length - 1 && turn.role === "assistant" ? applyEvents(turn, newEvents) : turn));
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, isStreaming]);

  const agentChoices = useMemo(() => skills.filter((skill) => !skill.name.includes("-")), [skills]);
  const skillChoices = useMemo(() => [{ name: "knowledge-graph-extraction", description: "从文档抽取知识图谱" }, ...skills.filter((skill) => skill.name.includes("-"))], [skills]);

  const handleSend = (prompt = input) => {
    const text = prompt.trim();
    if (!text || isStreaming || text.length > MAX_INPUT_LENGTH) return;
    processedEvents.current = 0;
    setTurns((previous) => [...previous, createTurn("user", text), { ...createTurn("assistant"), pending: true }]);
    send({ message: text, agent: selectedAgent || undefined, skill: selectedSkill || undefined, model: preferences.defaultModel || undefined, thinking, session_id: sessionId, profile_id: profileId, response_mode: "auto" });
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleStop = () => {
    stop();
    setTurns((previous) => previous.map((turn, index) => index === previous.length - 1 && turn.role === "assistant" ? { ...turn, pending: false, stopped: true } : turn));
  };

  const startNewConversation = () => {
    if (isStreaming) return;
    setTurns([]);
    setSessionId(crypto.randomUUID());
    setInput("");
    textareaRef.current?.focus();
  };

  return (
    <div className="flex h-dvh min-h-[580px] flex-col">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-200/80 bg-white/80 px-5 py-3.5 backdrop-blur sm:px-8">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600 text-white lg:hidden"><Bot size={19} /></div>
          <div><h1 className="text-[15px] font-semibold text-slate-800">智能对话</h1><p className="mt-0.5 text-xs text-slate-400">连接模型、工具与专业知识</p></div>
        </div>
        <button onClick={startNewConversation} disabled={isStreaming} className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"><Plus size={15} />新建会话</button>
      </header>

      <div className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex min-h-full w-full max-w-4xl flex-col px-5 py-7 sm:px-8">
              {turns.length === 0 ? <Welcome onPrompt={handleSend} /> : <Conversation turns={turns} />}
              <div ref={bottomRef} />
            </div>
          </div>
          <Composer input={input} setInput={setInput} inputRef={textareaRef} isStreaming={isStreaming} onSend={() => handleSend()} onStop={handleStop} selectedAgent={selectedAgent} setSelectedAgent={setSelectedAgent} selectedSkill={selectedSkill} setSelectedSkill={setSelectedSkill} agentChoices={agentChoices} skillChoices={skillChoices} thinking={thinking} setThinking={setThinking} skillsError={skillsError} />
        </section>
      </div>
    </div>
  );
}

function Welcome({ onPrompt }: { onPrompt: (prompt: string) => void }) {
  return <div className="m-auto w-full max-w-3xl pb-12 text-center fade-in"><div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-xl shadow-blue-200"><Sparkles size={27} /></div><h2 className="mt-6 text-2xl font-semibold tracking-tight text-slate-800 sm:text-[28px]">今天想让 Agent 帮你完成什么？</h2><p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-slate-500">选择一个任务开始，或直接描述你的目标。平台会自动路由到合适的 Agent 和工具。</p><div className="mt-9 grid gap-3 text-left sm:grid-cols-3">{suggestedPrompts.map(({ title, text, icon: Icon, tone }) => <button key={title} onClick={() => onPrompt(text)} className="group rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-lg hover:shadow-blue-100/50"><span className={`flex h-9 w-9 items-center justify-center rounded-xl ${tone === "blue" ? "bg-blue-50 text-blue-600" : tone === "violet" ? "bg-violet-50 text-violet-600" : "bg-amber-50 text-amber-600"}`}><Icon size={18} /></span><p className="mt-4 text-sm font-semibold text-slate-700">{title}</p><p className="mt-1 text-xs leading-5 text-slate-400">{text}</p></button>)}</div></div>;
}

function Conversation({ turns }: { turns: ChatTurn[] }) {
  return <div className="space-y-7">{turns.map((turn) => <div key={turn.id} className={`flex gap-3.5 slide-up ${turn.role === "user" ? "justify-end" : ""}`}>
    {turn.role === "assistant" && <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-md shadow-blue-100"><Bot size={16} /></div>}
    <div className={turn.role === "user" ? "max-w-[82%] rounded-2xl rounded-tr-md bg-slate-800 px-4 py-3 text-sm leading-6 text-white shadow-sm" : "min-w-0 max-w-[88%] flex-1 pt-1"}>
      {turn.role === "assistant" && <p className="mb-2 text-xs font-medium text-slate-400">Agent Studio</p>}
      {turn.activities.length > 0 && <ActivityList items={turn.activities} />}
      {turn.reasoning && <Reasoning content={turn.reasoning} />}
      {turn.content && <div className={`whitespace-pre-wrap text-sm leading-7 ${turn.role === "user" ? "text-white" : "text-slate-700"}`}>{turn.content}</div>}
      {turn.pending && !turn.content && <LoadingReply />}
      {turn.stopped && <p className="mt-2 text-xs text-slate-400">已停止生成</p>}
      {turn.error && <p className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{turn.error}</p>}
    </div>
  </div>)}</div>;
}

function Composer({ input, setInput, inputRef, isStreaming, onSend, onStop, selectedAgent, setSelectedAgent, selectedSkill, setSelectedSkill, agentChoices, skillChoices, thinking, setThinking, skillsError }: { input: string; setInput: (value: string) => void; inputRef: React.RefObject<HTMLTextAreaElement | null>; isStreaming: boolean; onSend: () => void; onStop: () => void; selectedAgent: string; setSelectedAgent: (value: string) => void; selectedSkill: string; setSelectedSkill: (value: string) => void; agentChoices: SkillInfo[]; skillChoices: { name: string; description: string }[]; thinking: boolean; setThinking: (value: boolean) => void; skillsError: boolean }) {
  return <div className="shrink-0 border-t border-slate-200/80 bg-white/85 px-5 py-4 backdrop-blur sm:px-8"><div className="mx-auto max-w-4xl"><div className="focus-ring overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><ExecutionSettings selectedAgent={selectedAgent} setSelectedAgent={setSelectedAgent} selectedSkill={selectedSkill} setSelectedSkill={setSelectedSkill} agentChoices={agentChoices} skillChoices={skillChoices} thinking={thinking} setThinking={setThinking} skillsError={skillsError} /><div className="flex items-end gap-2 px-3 py-2"><textarea ref={inputRef} value={input} maxLength={MAX_INPUT_LENGTH} rows={1} disabled={isStreaming} onChange={(event) => { setInput(event.target.value); event.currentTarget.style.height = "auto"; event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 150)}px`; }} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); onSend(); } }} placeholder="输入你的问题，按 Enter 发送…" className="max-h-[150px] min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-slate-700 placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed" />{isStreaming ? <button onClick={onStop} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-white transition hover:bg-slate-700" aria-label="停止生成"><CircleStop size={18} /></button> : <button onClick={onSend} disabled={!input.trim()} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white shadow-md shadow-blue-200 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:shadow-none" aria-label="发送消息"><ArrowUp size={19} strokeWidth={2.5} /></button>}</div></div><div className="mt-2 flex items-center justify-between px-2 text-[11px] text-slate-400"><span>Enter 发送 · Shift + Enter 换行</span><span>{input.length.toLocaleString()} / {MAX_INPUT_LENGTH.toLocaleString()}</span></div></div></div>;
}

function ExecutionSettings({ selectedAgent, setSelectedAgent, selectedSkill, setSelectedSkill, agentChoices, skillChoices, thinking, setThinking, skillsError }: { selectedAgent: string; setSelectedAgent: (value: string) => void; selectedSkill: string; setSelectedSkill: (value: string) => void; agentChoices: SkillInfo[]; skillChoices: { name: string; description: string }[]; thinking: boolean; setThinking: (value: boolean) => void; skillsError: boolean }) {
  const autoRoute = !selectedAgent && !selectedSkill;
  return <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 bg-slate-50/70 px-3 py-2"><div className="flex items-center gap-1.5 pr-1 text-[11px] font-semibold tracking-[.08em] text-slate-400"><Route size={14} />执行</div><SettingSelect label="Agent" value={selectedAgent} onChange={(value) => { setSelectedAgent(value); if (value) setSelectedSkill(""); }} options={[{ name: "", description: "选择 Agent" }, ...agentChoices]} compact /><SettingSelect label="Skill" value={selectedSkill} onChange={(value) => { setSelectedSkill(value); if (value) setSelectedAgent(""); }} options={[{ name: "", description: "选择 Skill" }, ...skillChoices]} compact /><div className="hidden h-5 w-px bg-slate-200 sm:block" /><label className={`flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition ${thinking ? "bg-violet-100/70 text-violet-700" : "text-slate-500 hover:bg-white hover:text-slate-700"}`}><input type="checkbox" checked={thinking} onChange={(event) => setThinking(event.target.checked)} className="sr-only" /><span className={`flex h-4 w-7 items-center rounded-full p-0.5 transition ${thinking ? "bg-violet-500" : "bg-slate-200"}`}><span className={`h-3 w-3 rounded-full bg-white shadow-sm transition ${thinking ? "translate-x-3" : ""}`} /></span><BrainCircuit size={14} />推理</label><span className={`ml-auto inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium ${autoRoute ? "text-blue-600" : "text-emerald-600"}`}><Sparkles size={13} />{autoRoute ? "自动路由" : "已指定"}</span>{skillsError && <span className="w-full pt-0.5 text-[11px] text-amber-600">Agent 列表加载失败，仍可使用自动路由。</span>}</div>;
}

function SettingSelect({ label, value, onChange, options, compact = false }: { label: string; value: string; onChange: (value: string) => void; options: { name: string; description: string }[]; compact?: boolean }) {
  return <label className={compact ? "relative" : "block"}>{!compact && <span className="mb-1.5 block text-xs font-medium text-slate-600">{label}</span>}<div className="relative"><select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} className={`focus-ring appearance-none border border-slate-200 bg-white text-xs font-medium text-slate-600 shadow-sm transition hover:border-slate-300 hover:text-slate-800 ${compact ? "h-8 w-36 rounded-lg pl-2.5 pr-7 sm:w-40" : "w-full rounded-xl px-3 py-2.5 pr-8"}`}><option value="">{options[0]?.description || "不指定"}</option>{options.slice(1).map((option) => <option key={option.name} value={option.name}>{option.name}</option>)}</select><ChevronDown size={13} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-slate-400" /></div></label>;
}

function applyEvents(turn: ChatTurn, events: SSEMessage[]): ChatTurn {
  const next = { ...turn, activities: [...turn.activities] };
  for (const event of events) {
    if (event.type === "delta") next.content += event.content || "";
    if (event.type === "thinking_delta") next.reasoning += event.content || "";
    if (event.type === "routing") next.activities.push({ kind: "route", label: `已路由至 ${event.skill || "通用助手"}`, detail: event.confidence !== undefined ? `置信度 ${Math.round(event.confidence * 100)}%` : undefined });
    if (event.type === "tool_start") next.activities.push({ kind: "tool", label: `正在调用 ${event.tool || "工具"}`, detail: event.input });
    if (event.type === "tool_end") next.activities.push({ kind: "status", label: `${event.tool || "工具"} 已完成`, detail: event.output });
    if (event.type === "tool_error") next.activities.push({ kind: "status", label: `${event.tool || "工具"} 调用失败`, detail: event.error });
    if (event.type === "error") next.error = event.error || "请求发生错误，请稍后重试。";
    if (event.type === "done") next.pending = false;
  }
  return next;
}

function ActivityList({ items }: { items: Activity[] }) {
  const [open, setOpen] = useState(false);
  return <div className="mb-3 rounded-xl border border-slate-200 bg-slate-50/80"><button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-500"><Wrench size={14} className="text-blue-500" /><span>{items.length} 条执行动态</span>{open ? <ChevronDown size={14} className="ml-auto" /> : <ChevronRight size={14} className="ml-auto" />}</button>{open && <div className="space-y-2 border-t border-slate-200 px-3 py-2.5">{items.map((item, index) => <div key={`${item.label}-${index}`} className="text-xs"><p className="text-slate-600">{item.label}</p>{item.detail && <p className="mt-1 max-h-20 overflow-auto whitespace-pre-wrap rounded bg-white px-2 py-1.5 text-[11px] leading-4 text-slate-400">{item.detail}</p>}</div>)}</div>}</div>;
}

function Reasoning({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  return <div className="mb-3 rounded-xl border border-violet-100 bg-violet-50/50"><button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-violet-700"><BrainCircuit size={14} />模型思考过程{open ? <ChevronDown size={14} className="ml-auto" /> : <ChevronRight size={14} className="ml-auto" />}</button>{open && <p className="max-h-52 overflow-y-auto whitespace-pre-wrap border-t border-violet-100 px-3 py-2.5 text-xs leading-5 text-violet-800/75">{content}</p>}</div>;
}

function LoadingReply() { return <div className="flex h-7 items-center gap-1.5"><LoaderCircle size={15} className="animate-spin text-blue-500" /><span className="text-xs text-slate-400">正在思考</span><span className="typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" /><span className="typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" /><span className="typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" /></div>; }
