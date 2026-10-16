"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth/AuthContext";

const LINKS = [{ href: "/app", label: "Decisions" }];

export function AppNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  function handleLogout() {
    logout();
    router.push("/");
  }

  return (
    <header className="sticky top-0 z-40 border-b border-white/5 bg-obsidian-950/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4 lg:px-10">
        <Link href="/app" className="label-mono text-ivory-100">
          MINDTRACE
        </Link>
        <nav className="flex items-center gap-6">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={clsx(
                "text-sm transition-colors",
                pathname === link.href
                  ? "text-ivory-100"
                  : "text-ivory-300/60 hover:text-ivory-100",
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-4">
          <span className="hidden text-sm text-ivory-300/50 sm:inline">{user?.email}</span>
          <Button variant="ghost" size="md" onClick={handleLogout}>
            Sign out
          </Button>
        </div>
      </div>
    </header>
  );
}
