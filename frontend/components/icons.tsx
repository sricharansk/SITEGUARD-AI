// Small inline icons (no icon library). All are decorative: the text next to them carries the meaning.
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 14, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

// Shapes used by risk and severity badges: circle < diamond < triangle < octagon.
export const CircleShape = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="8" cy="8" r="5" fill="currentColor" stroke="none" />
  </Svg>
);
export const DiamondShape = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 2.5 13.5 8 8 13.5 2.5 8Z" fill="currentColor" stroke="none" />
  </Svg>
);
export const TriangleShape = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 2 14.5 13.5h-13Z" fill="currentColor" stroke="none" />
    <path d="M8 6.5v3.2M8 11.6v.1" stroke="white" strokeWidth={1.6} />
  </Svg>
);
export const OctagonShape = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5.5 1.5h5l4 4v5l-4 4h-5l-4-4v-5Z" fill="currentColor" stroke="none" />
    <path d="M8 4.5v4.2M8 11.2v.1" stroke="white" strokeWidth={1.8} />
  </Svg>
);

export const CheckIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m3 8.5 3.2 3L13 4.5" />
  </Svg>
);
export const CrossIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m4 4 8 8M12 4l-8 8" />
  </Svg>
);
export const ClockIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="8" cy="8" r="6" />
    <path d="M8 4.5V8l2.5 1.5" />
  </Svg>
);
export const DotIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="8" cy="8" r="3" fill="currentColor" stroke="none" />
  </Svg>
);
export const RingIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="8" cy="8" r="5" />
  </Svg>
);
export const DashIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 8h8" />
  </Svg>
);
export const PencilIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10.5 2.5 13.5 5.5 6 13H3v-3Z" />
  </Svg>
);
export const SparkleIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 1.5 9.4 6.6 14.5 8 9.4 9.4 8 14.5 6.6 9.4 1.5 8 6.6 6.6Z" fill="currentColor" stroke="none" />
  </Svg>
);
export const ShieldIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 1.5 13.5 3.5v4c0 3.4-2.4 5.9-5.5 7-3.1-1.1-5.5-3.6-5.5-7v-4Z" />
    <path d="m5.5 8 1.8 1.8L10.8 6.3" />
  </Svg>
);
export const UserIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="8" cy="5.5" r="2.8" />
    <path d="M2.5 14c.6-2.8 2.8-4.3 5.5-4.3s4.9 1.5 5.5 4.3" />
  </Svg>
);
export const FileIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 1.5h5.5L12.5 4.5v10h-8.5Z" />
    <path d="M9.5 1.5v3h3" />
  </Svg>
);
export const DownloadIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 2v8M4.5 7 8 10.5 11.5 7M2.5 13.5h11" />
  </Svg>
);
export const AlertIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 1.8 15 14H1Z" />
    <path d="M8 6v3.5M8 11.6v.1" />
  </Svg>
);
export const LockIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="7" width="10" height="7.5" rx="1" />
    <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
  </Svg>
);
export const InfoIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="8" cy="8" r="6.2" />
    <path d="M8 7.2v4M8 4.8v.1" />
  </Svg>
);
export const HardHatIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2 11.5h12M3 11.5V10a5 5 0 0 1 10 0v1.5M6.5 5.3V3.5h3v1.8" />
    <path d="M1.5 13.5h13" />
  </Svg>
);
export const SpinnerIcon = ({ className = "", ...p }: IconProps) => (
  <Svg className={`animate-spin motion-reduce:animate-none ${className}`} {...p}>
    <path d="M8 1.75a6.25 6.25 0 1 0 6.25 6.25" />
  </Svg>
);
