"use client";

/**
 * Brand logos for the connectors marketplace, as inline SVG so they are
 * fully self-contained (no external hosts — the app CSP blocks them) and
 * theme-independent. Each mark is drawn on a white rounded tile
 * (`LogoTile`) so multi-colour marks read on both light and dark themes,
 * which is how real connector galleries present third-party brands.
 *
 * These approximate the official brand marks for recognition (nominative
 * use to indicate an integration); they are intentionally simple.
 */

type LogoProps = { size?: number };

export function LogoTile({
  id,
  size = 40,
}: {
  id: string;
  size?: number;
}) {
  const inner = Math.round(size * 0.62);
  const Logo = LOGOS[id];
  return (
    <div
      aria-hidden
      style={{
        width: size,
        height: size,
        borderRadius: Math.round(size * 0.26),
        background: "#FFFFFF",
        display: "grid",
        placeItems: "center",
        flexShrink: 0,
        boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.06)",
      }}
    >
      {Logo ? <Logo size={inner} /> : null}
    </div>
  );
}

function Gmail({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M3 18.7V8.2l3 2.2v8.9H4a1 1 0 0 1-1-1z" fill="#4285F4" />
      <path d="M18 19.3v-8.9l3-2.2v10.5a1 1 0 0 1-1 1z" fill="#FBBC04" />
      <path d="M6 19.3v-9l6 4.4 6-4.4v9l-6-4.1z" fill="#34A853" />
      <path
        d="M3 8.2V6.6c0-1 1.1-1.5 1.9-1L12 11l7.1-5.4c.8-.6 1.9 0 1.9 1v1.6l-9 6.6z"
        fill="#EA4335"
      />
    </svg>
  );
}

function Outlook({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="10" y="5" width="11" height="14" rx="1.4" fill="#0F6CBD" />
      <path d="M10 8h11M15.5 5v14" stroke="#fff" strokeWidth="1.1" opacity="0.5" />
      <rect x="2.5" y="6.5" width="11" height="11" rx="2.6" fill="#0A5AA8" />
      <circle cx="8" cy="12" r="3.1" fill="none" stroke="#fff" strokeWidth="1.7" />
    </svg>
  );
}

function HubSpot({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <g fill="#FF7A59">
        <path d="M15.5 8.9V6.3a1.7 1.7 0 1 0-1.6 0v2.6a5 5 0 0 0-2 .9L6 6.5a1.9 1.9 0 1 0-1 1.4l5.8 4.2a5 5 0 1 0 4.7-3.2zm-1 7.7a2.6 2.6 0 1 1 0-5.2 2.6 2.6 0 0 1 0 5.2z" />
      </g>
    </svg>
  );
}

function Pipedrive({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="#111827" />
      <path
        d="M12.6 6.6c-1.3 0-2.2.6-2.7 1.3l-.1-1.1H7.2c0 .5.1 1.2.1 2v9.9h2.6v-3.8c.5.5 1.3.9 2.4.9 2.4 0 4.1-1.9 4.1-4.6 0-2.7-1.6-4.5-3.8-4.5zm-.6 6.9c-1.1 0-1.9-.9-1.9-2.3s.8-2.3 1.9-2.3 1.8.9 1.8 2.3-.7 2.3-1.8 2.3z"
        fill="#fff"
      />
    </svg>
  );
}

function Notion({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="2.5" y="2.5" width="19" height="19" rx="4" fill="#0F0F0F" />
      <path
        d="M8 7.5l7 .5v9m-8-9.3 1.2.9v8.4l-1.2-.6zM8 7.5l7 9.5"
        stroke="#fff"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

function Sheets({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path
        d="M13 2.5H7A2.5 2.5 0 0 0 4.5 5v14A2.5 2.5 0 0 0 7 21.5h10a2.5 2.5 0 0 0 2.5-2.5V9z"
        fill="#0F9D58"
      />
      <path d="M13 2.5 19.5 9H14a1 1 0 0 1-1-1z" fill="#0B7C46" />
      <path
        d="M8 12h8m-8 2.6h8M8 17h8M11 11v7.6M14 11v7.6"
        stroke="#fff"
        strokeWidth="1.05"
      />
    </svg>
  );
}

function Slack({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M6.5 14.5a2 2 0 1 1-2-2h2zM7.5 14.5a2 2 0 0 1 4 0v5a2 2 0 0 1-4 0z" fill="#E01E5A" />
      <path d="M9.5 6.5a2 2 0 1 1 2-2v2zM9.5 7.5a2 2 0 0 1 0 4h-5a2 2 0 0 1 0-4z" fill="#36C5F0" />
      <path d="M17.5 9.5a2 2 0 1 1 2 2h-2zM16.5 9.5a2 2 0 0 1-4 0v-5a2 2 0 0 1 4 0z" fill="#2EB67D" />
      <path d="M14.5 17.5a2 2 0 1 1-2 2v-2zM14.5 16.5a2 2 0 0 1 0-4h5a2 2 0 0 1 0 4z" fill="#ECB22E" />
    </svg>
  );
}

function Make({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="#6D00CC" />
      <path
        d="M7 17V7.5l2.5 6 2.5-6 2.5 6 2.5-6V17"
        stroke="#fff"
        strokeWidth="1.7"
        strokeLinejoin="round"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

function Hunter({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="#FF5100" />
      <circle cx="12" cy="12" r="5.2" fill="none" stroke="#fff" strokeWidth="1.7" />
      <circle cx="12" cy="12" r="1.7" fill="#fff" />
      <path d="M12 4.5v2M12 17.5v2M4.5 12h2M17.5 12h2" stroke="#fff" strokeWidth="1.4" />
    </svg>
  );
}

function Proxycurl({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="#4F46E5" />
      <path
        d="M10.2 13.8 8.8 15.2a2.3 2.3 0 0 1-3.3-3.3l1.9-1.9a2.3 2.3 0 0 1 3.3 0M13.8 10.2l1.4-1.4a2.3 2.3 0 0 1 3.3 3.3l-1.9 1.9a2.3 2.3 0 0 1-3.3 0"
        stroke="#fff"
        strokeWidth="1.6"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

function Adzuna({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="#9B1B8F" />
      <path
        d="M8 16.5 12 7l4 9.5M9.4 13.6h5.2"
        stroke="#fff"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}

function CompaniesHouse({ size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="#1D70B8" />
      <path
        d="M6.5 17.5h11M8 17.5v-6M12 17.5v-6M16 17.5v-6M6 11h12L12 6z"
        stroke="#fff"
        strokeWidth="1.4"
        strokeLinejoin="round"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

const LOGOS: Record<string, (p: LogoProps) => JSX.Element> = {
  gmail: Gmail,
  outlook: Outlook,
  hubspot: HubSpot,
  pipedrive: Pipedrive,
  notion: Notion,
  sheets: Sheets,
  slack: Slack,
  make: Make,
  hunter: Hunter,
  proxycurl: Proxycurl,
  adzuna: Adzuna,
  companies_house: CompaniesHouse,
};
