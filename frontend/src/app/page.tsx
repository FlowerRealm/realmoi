"use client";

import { RequireAuth } from "@/components/RequireAuth";
import { AssistantApp } from "@/components/assistant/AssistantApp";
import { AppHeader } from "@/components/AppHeader";

export default function Home() {
  return (
    <RequireAuth>
      <AppHeader mode="overlay" />
      <AssistantApp />
    </RequireAuth>
  );
}
