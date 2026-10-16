import { forwardRef } from "react";
import Link from "next/link";
import clsx from "clsx";

type Variant = "primary" | "secondary" | "ghost";
type Size = "md" | "lg";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-ivory-100 text-obsidian-950 hover:bg-white shadow-[0_0_0_1px_rgba(255,255,255,0.1)]",
  secondary: "glass-panel text-ivory-100 hover:bg-white/[0.08]",
  ghost: "text-ivory-200 hover:text-ivory-100 hover:bg-white/[0.05]",
};

const sizeClasses: Record<Size, string> = {
  md: "px-5 py-2.5 text-sm",
  lg: "px-7 py-3.5 text-base",
};

export function buttonClassName(variant: Variant = "primary", size: Size = "md", className?: string) {
  return clsx(
    "inline-flex items-center justify-center gap-2 rounded-full font-medium transition-all duration-200",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lavender-400 focus-visible:ring-offset-2 focus-visible:ring-offset-obsidian-950",
    "disabled:cursor-not-allowed disabled:opacity-40",
    variantClasses[variant],
    sizeClasses[size],
    className,
  );
}

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className, children, ...props }, ref) => {
    return (
      <button ref={ref} className={buttonClassName(variant, size, className)} {...props}>
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";

interface ButtonLinkProps extends React.ComponentPropsWithoutRef<typeof Link> {
  variant?: Variant;
  size?: Size;
}

export const ButtonLink = forwardRef<HTMLAnchorElement, ButtonLinkProps>(
  ({ variant = "primary", size = "md", className, children, ...props }, ref) => {
    return (
      <Link ref={ref} className={buttonClassName(variant, size, className)} {...props}>
        {children}
      </Link>
    );
  },
);
ButtonLink.displayName = "ButtonLink";
