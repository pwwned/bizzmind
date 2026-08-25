/* Bizzmind mark: bars (data) + pie (result). Source of truth: brand/bizzmind-mark-*.svg */
export function Mark({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={className} aria-hidden="true">
      <path d="M28.0 8.00 H5.42 a3.42 3.42 0 0 0 0 6.83 H28.0 Z" fill="#e9f08e" />
      <path d="M28.0 16.23 H10.22 a3.42 3.42 0 0 0 0 6.83 H28.0 Z" fill="#b5d33d" />
      <path d="M28.0 24.47 H14.22 a3.42 3.42 0 0 0 0 6.83 H28.0 Z" fill="#b5d33d" />
      <path d="M28.0 32.70 H17.52 a3.42 3.42 0 0 0 0 6.83 H28.0 Z" fill="#93ad35" />
      <path d="M28.0 40.93 H20.22 a3.42 3.42 0 0 0 0 6.83 H28.0 Z" fill="#6f8f1f" />
      <path d="M28.0 49.17 H22.42 a3.42 3.42 0 0 0 0 6.83 H28.0 Z" fill="#6f8f1f" />
      <path d="M29.40 39.02 L29.40 24.47 A14.55 14.55 0 0 1 42.00 31.74 Z" fill="#e9f08e" />
      <path d="M30.10 40.23 L42.70 32.96 A14.55 14.55 0 0 1 42.70 47.51 Z" fill="#43582f" />
      <path d="M29.40 41.45 L42.00 48.72 A14.55 14.55 0 0 1 29.40 56.00 Z" fill="#2f4026" />
    </svg>
  );
}

export function Wordmark({ size = 20 }: { size?: number }) {
  return (
    <span className="font-heading font-extrabold tracking-tight" style={{ fontSize: size }}>
      Bizz<span className="text-grad-olive">mind</span>
    </span>
  );
}

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <Mark size={size} className="drop-shadow-[0_0_12px_rgba(181,211,61,0.35)]" />
      <Wordmark size={Math.round(size * 0.7)} />
    </span>
  );
}
