type Props = { className?: string };

export default function Wordmark({ className = '' }: Props) {
  return <span className={`wordmark ${className}`.trim()}>LandLens</span>;
}
