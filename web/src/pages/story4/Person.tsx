// A tiny neutral person: head and shoulders, no face, no gender cues. Used at 22-28px.
export default function Person({ size = 26 }: { size?: number }) {
  return (
    <svg className="s4-person" width={size} height={size * 1.1} viewBox="0 0 24 27" aria-hidden="true">
      <circle cx="12" cy="7" r="5" />
      <path d="M2 27v-4.5a10 10 0 0 1 20 0V27z" />
    </svg>
  );
}
