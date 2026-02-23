<script lang="ts">
  import { onMount, onDestroy } from "svelte";

  interface ActiveContext {
    app_name: string;
    window_title: string;
    file_path: string | null;
    icon: string;
  }

  let context = $state<ActiveContext | null>(null);
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  let displayText = $derived.by(() => {
    if (!context || (!context.app_name && !context.window_title)) {
      return "Ready to help";
    }

    // If we have a window title, extract meaningful part
    const title = context.window_title;
    if (title) {
      // Many apps put "filename - AppName" or "AppName - filename"
      // Show the shorter meaningful part
      const parts = title.split(" - ");
      if (parts.length > 1) {
        // Return the part that looks like a filename (shorter, has extension)
        const candidate = parts[0].trim();
        if (candidate.includes(".") || candidate.length < parts[parts.length - 1].trim().length) {
          return candidate;
        }
        return parts[parts.length - 1].trim();
      }
      return title;
    }

    if (context.file_path) {
      // Show just the last folder/file from path
      const segments = context.file_path.split("/");
      return segments[segments.length - 1] || context.file_path;
    }

    return context.app_name;
  });

  let icon = $derived(context?.icon ?? "🐾");

  /** Export context for parent to include in messages */
  export function getContext(): ActiveContext | null {
    return context;
  }

  async function pollContext() {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const result = await invoke<ActiveContext>("get_active_context");
      context = result;
    } catch {
      // Not in Tauri or command failed — leave as null
    }
  }

  onMount(() => {
    pollContext();
    pollTimer = setInterval(pollContext, 2000);
  });

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });
</script>

<div class="flex items-center gap-2 border-b border-border/30 px-3 py-2">
  <span class="text-sm">{icon}</span>
  <div class="min-w-0 flex-1">
    <p class="text-[10px] text-muted-foreground/60">Working on:</p>
    <p class="truncate text-xs text-foreground/80">{displayText}</p>
  </div>
</div>
