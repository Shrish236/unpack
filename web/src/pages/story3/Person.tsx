// A tiny neutral person: a head and shoulders, no face, no gender cues. Labelled by role in the scene, never by name.
export default function Person({ tone = "ink", size = 28 }: { tone?: "ink" | "human"; size?: number }) {
  return (
    <svg className={`s3-pp ${tone}`} width={size * 0.72} height={size} viewBox="0 0 20 28" aria-hidden="true">
      <circle cx="10" cy="6" r="4.6" />
      <path d="M2.5 27v-6.5a7.5 7.5 0 0 1 15 0V27z" />
    </svg>
  );
}
