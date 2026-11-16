// One drawing system for every glyph: a 24 grid, 2.75 stroke, square ends.

type IconProps = { className?: string };

function Svg({ className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.75}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
      className={className ?? "h-[1em] w-[1em]"}
    >
      {children}
    </svg>
  );
}

const TURN = { right: 0, down: 90, left: 180, up: 270, "up-right": 315 } as const;

export function Arrow({
  to = "right",
  className,
}: IconProps & { to?: keyof typeof TURN }) {
  return (
    <Svg className={className}>
      <g transform={`rotate(${TURN[to]} 12 12)`}>
        <path d="M4 12h14" />
        <path d="M13 5.5l6.5 6.5-6.5 6.5" />
      </g>
    </Svg>
  );
}

export function Check({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M4.5 12.5l5 5 10-11" />
    </Svg>
  );
}

export function Cross({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Svg>
  );
}

export function Dash({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M6 12h12" />
    </Svg>
  );
}

export function Menu({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Svg>
  );
}
