import MouseScribe from './MouseScribe';
import './AgentCompanion.css';

type Props = { message: string; detail?: string };

/** The Deep Agent's companion: the note-taking mouse, walking and scribbling while the agent works. */
export default function AgentCompanion({ message, detail }: Props) {
  return <div className="agent-companion" aria-hidden="true">
    <div className="agent-companion-bubble">
      <span>{message}</span>
      {detail && <small>{detail}</small>}
    </div>
    <div className="agent-companion-character">
      <MouseScribe writing thinking lines={4} />
    </div>
  </div>;
}
