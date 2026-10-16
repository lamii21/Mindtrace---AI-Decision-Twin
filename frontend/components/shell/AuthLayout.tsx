import Link from "next/link";
import { Card } from "@/components/ui/Card";

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <main className="relative flex min-h-screen items-center justify-center bg-atmosphere px-6 py-16">
      <div className="pointer-events-none absolute inset-0 bg-radial-fade from-lavender-600/8 via-transparent to-transparent" />
      <div className="relative w-full max-w-md">
        <Link href="/" className="label-mono mb-10 block text-center text-ivory-300/60">
          MINDTRACE
        </Link>
        <Card className="p-8">
          <h1 className="font-display text-2xl text-ivory-100">{title}</h1>
          <p className="mt-2 text-sm text-ivory-300/60">{subtitle}</p>
          <div className="mt-8">{children}</div>
        </Card>
        <p className="mt-6 text-center text-sm text-ivory-300/50">{footer}</p>
      </div>
    </main>
  );
}
