"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AuthLayout } from "@/components/shell/AuthLayout";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { useAuth } from "@/lib/auth/AuthContext";
import Link from "next/link";

const MIN_PASSWORD_LENGTH = 12;

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(new Error(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`));
      return;
    }
    setLoading(true);
    try {
      await register(email, password);
      router.push("/app");
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout
      title="Create your twin"
      subtitle="Your decisions stay yours — encrypted at rest, scoped only to you."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="text-lavender-300 hover:text-lavender-200">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <div>
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
          />
        </div>
        <ErrorMessage error={error} />
        <Button type="submit" size="lg" className="w-full" disabled={loading}>
          {loading ? "Creating your twin…" : "Create account"}
        </Button>
      </form>
    </AuthLayout>
  );
}
