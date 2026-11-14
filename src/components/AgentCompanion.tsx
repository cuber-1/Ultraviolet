import './AgentCompanion.css';

type Props = { message: string; detail?: string };

export default function AgentCompanion({ message, detail }: Props) {
  return <div className="agent-companion" aria-hidden="true">
    <div className="agent-companion-bubble">
      <span>{message}</span>
      {detail && <small>{detail}</small>}
    </div>
    <div className="agent-companion-character">
      <svg viewBox="0 0 112 132" role="img" aria-label="Deep Agent working">
        <ellipse className="agent-companion-shadow" cx="56" cy="123" rx="31" ry="6" />
        <g className="agent-companion-body">
          <path className="agent-companion-arm agent-companion-arm-back" d="M34 76 C20 84 19 98 27 105" />
          <path className="agent-companion-arm agent-companion-arm-front" d="M78 76 C92 83 94 96 86 104" />
          <path className="agent-companion-leg agent-companion-leg-back" d="M47 105 L41 121" />
          <path className="agent-companion-leg agent-companion-leg-front" d="M65 105 L72 121" />
          <rect className="agent-companion-torso" x="31" y="59" width="50" height="51" rx="22" />
          <circle className="agent-companion-head" cx="56" cy="40" r="31" />
          <path className="agent-companion-highlight" d="M34 31 C40 17 56 12 68 18" />
          <g className="agent-companion-face">
            <ellipse className="agent-companion-eye" cx="46" cy="40" rx="3.5" ry="5" />
            <ellipse className="agent-companion-eye" cx="66" cy="40" rx="3.5" ry="5" />
            <path className="agent-companion-smile" d="M48 51 Q56 57 64 51" />
          </g>
          <circle className="agent-companion-badge" cx="56" cy="80" r="8" />
          <path className="agent-companion-spark" d="M56 74 L58 79 L63 81 L58 83 L56 88 L54 83 L49 81 L54 79 Z" />
        </g>
      </svg>
    </div>
  </div>;
}
