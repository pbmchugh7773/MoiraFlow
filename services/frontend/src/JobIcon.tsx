// Line icons per job type — stroke uses currentColor so they pick up the type tint.
// Keep these recognizable at small sizes; add a path when a new job type lands.

const PATHS: Record<string, JSX.Element> = {
  command: (
    <>
      <rect x="1.5" y="2.5" width="13" height="11" rx="1.5" />
      <path d="M4 6l2 2-2 2M8.5 10.5h3.5" />
    </>
  ),
  rest: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M2 8h12M8 2c2.2 2 2.2 10 0 12M8 2c-2.2 2-2.2 10 0 12" />
    </>
  ),
  sql: (
    <>
      <ellipse cx="8" cy="3.6" rx="5.3" ry="2" />
      <path d="M2.7 3.6v8.8c0 1.1 2.37 2 5.3 2s5.3-.9 5.3-2V3.6" />
      <path d="M2.7 8c0 1.1 2.37 2 5.3 2s5.3-.9 5.3-2" />
    </>
  ),
  transform: (
    <>
      <path d="M6.5 2.5c-2 0-1.5 2.2-1.5 3.3 0 1.1-.8 1.7-1.8 2.2 1 .5 1.8 1.1 1.8 2.2 0 1.1-.5 3.3 1.5 3.3" />
      <path d="M9.5 2.5c2 0 1.5 2.2 1.5 3.3 0 1.1.8 1.7 1.8 2.2-1 .5-1.8 1.1-1.8 2.2 0 1.1.5 3.3-1.5 3.3" />
    </>
  ),
  file_transfer: (
    <>
      <path d="M2.5 5.5h9.5" />
      <path d="M9 3l3 2.5-3 2.5" />
      <path d="M13.5 10.5H4" />
      <path d="M7 8l-3 2.5 3 2.5" />
    </>
  ),
};

export function JobIcon({ type, size = 15 }: { type: string; size?: number }) {
  const path = PATHS[type] ?? PATHS.command;
  return (
    <svg
      viewBox="0 0 16 16"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {path}
    </svg>
  );
}
