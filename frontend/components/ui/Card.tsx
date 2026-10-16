import clsx from "clsx";

export function Card({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx("glass-panel rounded-2xl shadow-glass", className)}
      {...props}
    >
      {children}
    </div>
  );
}
