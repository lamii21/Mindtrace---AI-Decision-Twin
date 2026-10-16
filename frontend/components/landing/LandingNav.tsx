import Link from "next/link";
import { ButtonLink } from "@/components/ui/Button";

export function LandingNav() {
  return (
    <header className="fixed inset-x-0 top-0 z-50 flex items-center justify-between px-6 py-5 lg:px-10">
      <Link href="/" className="label-mono text-ivory-100">
        MINDTRACE
      </Link>
      <nav className="hidden items-center gap-8 text-sm text-ivory-300/70 sm:flex">
        <Link href="#structure" className="transition-colors hover:text-ivory-100">
          How it works
        </Link>
        <Link href="/login" className="transition-colors hover:text-ivory-100">
          Sign in
        </Link>
      </nav>
      <ButtonLink size="md" href="/register" className="sm:hidden">
        Start
      </ButtonLink>
      <ButtonLink size="md" href="/register" className="hidden sm:inline-flex">
        Explore a decision
      </ButtonLink>
    </header>
  );
}
