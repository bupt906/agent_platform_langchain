import { useState, useEffect, useRef } from "react";
import { Send, Square, Brain, ChevronDown, ChevronRight, Wrench, Copy, Check } from "lucide-react";
import { useSSE, type SSEMessage } from "../hooks/useSSE";
import { api, type SkillInfo } from "../lib/api";

const MAX_INPUT_LENGTH = 10_000;

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [skillsError, setSkillsError] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState("");
  const [selectedAgent, setSelectedAgent] = useState("");
  const [thinking, setThinking] = useState(false);
  const [sessionId] = useState(() => crypto.randomUUID());
  const { messages, isStreaming, send, stop } = useSSE();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getSkills()
      .then(d => setSkills(d.skills || []))
      .catch(() => setSkillsError(true));
  }, []);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming || trimmed.length > MAX_INPUT_LENGTH) return;
    send({ message: trimmed, agent: selectedAgent || undefined, skill: selectedSkill || undefined, thinking, session_id: sessionId });
    setInput("");
  };

  // 通过 API 返回的 skill name 是否包含 "-" 来区分 agent 和声明式 skill
  // agent name 不含连字符（如 document_review），声明式 skill 含连字符（如 knowledge-graph-extraction）
  const agents = skills.filter(s => !s.name.includes("-"));
  const declarativeSkills = skills.filter(s => s.name.includes("-"));

  return (
    <div className="flex flex-col h-full">
      {/* header */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-gray-200 bg-white">
        <select className="text-sm border rounded-lg px-3 py-1.5 bg-white" value={selectedAgent} onChange={e => { setSelectedAgent(e.target.value); setSelectedSkill(""); }}>
          <option value="">自动选择 Agent</option>
          {agents.map(s => <option key={s.name} value={s.name}>{s.name}</option>)}
        </select>
        <select className="text-sm border rounded-lg px-3 py-1.5 bg-white" value={selectedSkill} onChange={e => { setSelectedSkill(e.target.value); setSelectedAgent(""); }}>
          <option value="">自动选择 Skill</option>
          {declarativeSkills.map(s => <option key={s.name} value={s.name}>{s.name}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer">
          <input type="checkbox" checked={thinking} onChange={e => setThinking(e.target.checked)} className="rounded" />
          <Brain size={14} /> 思考
        </label>
        {skillsError && <span className="text-xs text-red-400">技能列表加载失败</span>}
      </div>

      {/* messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-20">
            <p className="text-lg mb-2">智能体中台</p>
            <p className="text-sm">选择 Agent 或 Skill 开始对话</p>
          </div>
        )}
        {messages.map((m, i) => <ChatItem key={i} msg={m} />)}
        {isStreaming && <div className="typing text-blue-500 text-sm">思考中</div>}
        <div ref={bottomRef} />
      </div>

      {/* input */}
      <div className="px-6 py-4 border-t border-gray-200 bg-white">
        <div className="flex gap-2">
          <input
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-blue-400"
            placeholder="输入消息..."
            maxLength={MAX_INPUT_LENGTH}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          />
          {isStreaming ? (
            <button onClick={stop} aria-label="停止生成" className="p-2.5 bg-red-500 text-white rounded-lg hover:bg-red-600"><Square size={18} /></button>
          ) : (
            <button onClick={handleSend} disabled={!input.trim()} aria-label="发送消息" className="p-2.5 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"><Send size={18} /></button>
          )}
        </div>
        {input.length > MAX_INPUT_LENGTH && <p className="text-xs text-red-400 mt-1">消息过长（{input.length}/{MAX_INPUT_LENGTH}）</p>}
      </div>
    </div>
  );
}

function ChatItem({ msg }: { msg: SSEMessage }) {
  switch (msg.type) {
    case "routing":
      return <div className="text-xs text-gray-400 text-center">路由: {msg.skill} (置信度 {msg.confidence})</div>;
    case "thinking_delta":
      return <Collapsible title="思考过程" content={msg.content || ""} />;
    case "delta":
      return <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{msg.content}</div>;
    case "tool_start":
      return <ToolCard name={msg.tool || ""} input={msg.input} />;
    case "tool_end":
      return <div className="text-xs text-gray-400">✓ {msg.tool} 完成</div>;
    case "tool_error":
      return <div className="text-xs text-red-500">✗ {msg.tool}: {msg.error}</div>;
    case "model_end":
      return <div className="text-xs text-gray-300 text-center">— 结束 —</div>;
    case "error":
      return <div className="text-sm text-red-500">错误: {msg.error}</div>;
    case "done":
      return <div className="text-xs text-gray-300 text-center">— 完成 —</div>;
    default:
      return null;
  }
}

function Collapsible({ title, content }: { title: string; content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-gray-50 rounded-lg p-3 text-xs">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-1 text-gray-500 hover:text-gray-700">
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />} {title}
      </button>
      {open && <div className="mt-2 text-gray-600 whitespace-pre-wrap">{content}</div>}
    </div>
  );
}

function ToolCard({ name, input }: { name: string; input?: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!input) return;
    try {
      await navigator.clipboard.writeText(input);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // 剪贴板权限被拒绝（HTTP 环境等），静默失败
    }
  };

  return (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-2.5 text-xs">
      <div className="flex items-center gap-2">
        <Wrench size={14} className="text-amber-600" />
        <span className="font-medium text-amber-800">{name}</span>
        <button onClick={() => setOpen(!open)} className="text-amber-600 ml-auto">{open ? "收起" : "展开"}</button>
        {input && (
          <button onClick={handleCopy} aria-label="复制工具输入" className="text-gray-400 hover:text-gray-600">
            {copied ? <Check size={12} /> : <Copy size={12} />}
          </button>
        )}
      </div>
      {open && input && <pre className="mt-2 bg-amber-100 p-2 rounded text-gray-700 whitespace-pre-wrap max-h-40 overflow-y-auto">{input}</pre>}
    </div>
  );
}
