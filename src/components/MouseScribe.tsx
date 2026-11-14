import './MouseScribe.css';

/**
 * Ultraviolet's mascot: a little scholar mouse with round glasses who takes notes.
 * `writing` animates the pencil and draws fresh lines on the notepad; `lines` sets how
 * many lines are on the page (e.g. one per onboarding answer). Pure SVG + CSS.
 */
export default function MouseScribe({ writing = true, lines = 4, thinking = false, className = '' }: { writing?: boolean; lines?: number; thinking?: boolean; className?: string }) {
  const shown = Math.max(0, Math.min(5, lines));
  return <svg className={`mouse-scribe${writing ? ' writing' : ''}${thinking ? ' thinking' : ''} ${className}`.trim()} viewBox="0 0 170 180" role="img" aria-label="Ultraviolet's note-taking mouse">
    <defs>
      <radialGradient id="ms-fur" cx="45%" cy="35%" r="70%"><stop offset="0%" stopColor="#d9cec4" /><stop offset="70%" stopColor="#b9aca1" /><stop offset="100%" stopColor="#9f9288" /></radialGradient>
      <radialGradient id="ms-ear" cx="50%" cy="45%" r="60%"><stop offset="0%" stopColor="#f6c4c1" /><stop offset="100%" stopColor="#e39c99" /></radialGradient>
      <linearGradient id="ms-belly" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#fbf6f0" /><stop offset="100%" stopColor="#ece2d8" /></linearGradient>
      <linearGradient id="ms-pencil" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="#f7c548" /><stop offset="100%" stopColor="#e8a92a" /></linearGradient>
    </defs>

    <ellipse className="ms-shadow" cx="86" cy="171" rx="46" ry="6" />
    <path className="ms-tail" d="M118 150 C150 152 160 132 150 118 C142 106 128 112 134 122" />

    <g className="ms-body">
      <ellipse cx="86" cy="128" rx="40" ry="42" fill="url(#ms-fur)" />
      <ellipse cx="86" cy="136" rx="26" ry="30" fill="url(#ms-belly)" />
      <ellipse className="ms-foot" cx="68" cy="166" rx="12" ry="6" />
      <ellipse className="ms-foot" cx="104" cy="166" rx="12" ry="6" />

      <g className="ms-head">
        <g className="ms-ear ms-ear-left"><circle cx="48" cy="38" r="24" fill="url(#ms-fur)" /><circle cx="48" cy="39" r="15" fill="url(#ms-ear)" /></g>
        <g className="ms-ear ms-ear-right"><circle cx="124" cy="38" r="24" fill="url(#ms-fur)" /><circle cx="124" cy="39" r="15" fill="url(#ms-ear)" /></g>
        <ellipse cx="86" cy="70" rx="40" ry="37" fill="url(#ms-fur)" />
        <path d="M60 46 C70 36 98 34 110 44" fill="none" stroke="rgba(255,255,255,.45)" strokeWidth="5" strokeLinecap="round" />
        <ellipse className="ms-cheek" cx="58" cy="84" rx="8" ry="5" />
        <ellipse className="ms-cheek" cx="114" cy="84" rx="8" ry="5" />
        <ellipse cx="86" cy="88" rx="17" ry="12" fill="#efe5db" />
        <g className="ms-eyes">
          <ellipse cx="72" cy="68" rx="5.2" ry="6.6" fill="#2a201b" /><circle cx="73.8" cy="65.6" r="1.9" fill="#fff" />
          <ellipse cx="100" cy="68" rx="5.2" ry="6.6" fill="#2a201b" /><circle cx="101.8" cy="65.6" r="1.9" fill="#fff" />
        </g>
        <g className="ms-glasses" fill="none" stroke="#5b4a3f" strokeWidth="2.2"><circle cx="72" cy="68" r="11" /><circle cx="100" cy="68" r="11" /><path d="M83 67 Q86 64 89 67" /><path d="M61 66 L52 62" /><path d="M111 66 L120 62" /></g>
        <ellipse cx="86" cy="81" rx="5.5" ry="4.2" fill="#e57f84" /><ellipse cx="84.5" cy="79.8" rx="1.6" ry="1" fill="#fff" opacity=".7" />
        <path d="M86 85 L86 89 M80 91 Q86 95 92 91" fill="none" stroke="#7d5f55" strokeWidth="1.8" strokeLinecap="round" />
        <g className="ms-whiskers" stroke="#8a7b71" strokeWidth="1.1" strokeLinecap="round"><path d="M70 86 L44 80" /><path d="M70 89 L43 90" /><path d="M71 92 L46 99" /><path d="M102 86 L128 80" /><path d="M102 89 L129 90" /><path d="M101 92 L126 99" /></g>
      </g>

      <g className="ms-notepad">
        <rect x="40" y="104" width="44" height="54" rx="4" fill="#fffaf1" stroke="#d7c6b2" strokeWidth="1.5" />
        <rect x="40" y="104" width="44" height="8" rx="3" fill="#e85d04" />
        {[0, 1, 2, 3, 4].map((index) => <line key={index} x1="46" x2={index % 2 ? 72 : 78} y1={120 + index * 7.5} y2={120 + index * 7.5} className={`ms-line${index < shown ? ' on' : ''}${index === shown - 1 ? ' latest' : ''}`} />)}
        <ellipse cx="44" cy="134" rx="7" ry="6" fill="url(#ms-fur)" />
      </g>

      <g className="ms-pencil-arm">
        <ellipse cx="96" cy="126" rx="7" ry="6" fill="url(#ms-fur)" />
        <g transform="rotate(-38 96 126)">
          <rect x="94" y="96" width="7" height="30" rx="1.5" fill="url(#ms-pencil)" />
          <rect x="94" y="93" width="7" height="5" rx="1.5" fill="#f2a1a8" />
          <path d="M94 126 L97.5 134 L101 126 Z" fill="#f3d9b1" /><path d="M96.4 131.5 L97.5 134 L98.6 131.5 Z" fill="#3a2e28" />
        </g>
      </g>
    </g>

    <g className="ms-thought"><circle cx="138" cy="34" r="3.5" /><circle cx="148" cy="22" r="5" /><circle cx="160" cy="8" r="6.5" /></g>
  </svg>;
}
