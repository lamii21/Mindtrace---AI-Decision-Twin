"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { createDecision } from "@/lib/api/decisions";
import type { DecisionCategory, OptionIn } from "@/lib/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Label, Textarea } from "@/components/ui/Input";
import { ErrorMessage } from "@/components/ui/ErrorMessage";

const CATEGORIES: { value: DecisionCategory; label: string }[] = [
  { value: "career", label: "Career" },
  { value: "education", label: "Education" },
  { value: "project", label: "Project" },
  { value: "purchase", label: "Purchase" },
  { value: "relationship", label: "Relationship" },
  { value: "other", label: "Other" },
];

export default function NewDecisionPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<DecisionCategory>("career");
  const [context, setContext] = useState("");
  const [option, setOption] = useState<OptionIn>({ id: "accept", label: "", body: "" });

  const mutation = useMutation({
    mutationFn: createDecision,
    onSuccess: (decision) => router.push(`/app/decisions/${decision.id}`),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    mutation.mutate({
      title,
      category,
      context,
      options: [{ ...option, id: option.id || "accept" }],
    });
  }

  const canSubmit = title.trim().length > 0 && context.trim().length > 0 && option.label.trim().length > 0;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-display text-3xl text-ivory-100">Describe the decision</h1>
      <p className="mt-2 text-sm text-ivory-300/60">
        Write it the way you&apos;d explain it to a friend. The more context you give, the more
        factors MINDTRACE can extract.
      </p>

      <Card className="mt-8 p-8">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <Label htmlFor="title">Title</Label>
            <Input
              id="title"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Should I take the new job?"
            />
          </div>

          <div>
            <Label htmlFor="category">Category</Label>
            <select
              id="category"
              value={category}
              onChange={(e) => setCategory(e.target.value as DecisionCategory)}
              className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-ivory-100 focus:border-lavender-400/50 focus:outline-none focus:ring-2 focus:ring-lavender-400/20"
            >
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value} className="bg-obsidian-900">
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <Label htmlFor="context">Context</Label>
            <Textarea
              id="context"
              required
              rows={6}
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="Describe the situation: what's on the table, what matters to you, what you're weighing..."
            />
          </div>

          <div>
            <Label htmlFor="option-label">The option you&apos;re considering</Label>
            <Input
              id="option-label"
              required
              value={option.label}
              onChange={(e) => setOption((o) => ({ ...o, label: e.target.value }))}
              placeholder="e.g. Accept the offer"
            />
            <Textarea
              className="mt-3"
              rows={2}
              value={option.body}
              onChange={(e) => setOption((o) => ({ ...o, body: e.target.value }))}
              placeholder="Optional detail about this option"
            />
          </div>

          <ErrorMessage error={mutation.error} />

          <Button type="submit" size="lg" className="w-full" disabled={!canSubmit || mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Save decision"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
