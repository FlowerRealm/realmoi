"use client";

import { RequireAuth } from "@/components/RequireAuth";
import { AppHeader } from "@/components/AppHeader";
import { AssistantApp } from "@/components/assistant/AssistantApp";

export default function Home() {
  return (
    <RequireAuth>
      <AppHeader mode="overlay" />
      <AssistantApp />
    </RequireAuth>
  );
}
