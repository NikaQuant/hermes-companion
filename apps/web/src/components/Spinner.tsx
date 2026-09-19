export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <span className="spinner-wrap" role="status"><span className="spinner" /> <span>{label}</span></span>
}
