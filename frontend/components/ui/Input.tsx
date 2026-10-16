import { forwardRef } from "react";
import clsx from "clsx";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={clsx(
        "w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-ivory-100 placeholder:text-ivory-300/40",
        "focus:border-lavender-400/50 focus:outline-none focus:ring-2 focus:ring-lavender-400/20",
        "transition-colors duration-200",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={clsx(
      "w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-ivory-100 placeholder:text-ivory-300/40",
      "focus:border-lavender-400/50 focus:outline-none focus:ring-2 focus:ring-lavender-400/20",
      "transition-colors duration-200",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";

export function Label({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label className="label-mono mb-2 block text-ivory-300/70" {...props}>
      {children}
    </label>
  );
}
