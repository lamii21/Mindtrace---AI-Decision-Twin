import { RequireAuth } from "@/components/shell/RequireAuth";
import { AppNav } from "@/components/shell/AppNav";

export default function AppShellLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <div className="min-h-screen bg-obsidian-950">
        <AppNav />
        <main className="mx-auto max-w-6xl px-6 py-10 lg:px-10">{children}</main>
      </div>
    </RequireAuth>
  );
}
