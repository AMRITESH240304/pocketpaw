<script lang="ts">
  import { platform } from "@tauri-apps/plugin-os";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { PanelLeft } from "@lucide/svelte";
  import WindowControls from "./WindowControls.svelte";
  import SessionTitle from "./SessionTitle.svelte";
  import ModelBadge from "./ModelBadge.svelte";
  import QuickActions from "./QuickActions.svelte";
  import ConnectionBadge from "./ConnectionBadge.svelte";
  import AgentProgressBar from "./AgentProgressBar.svelte";

  let { onToggleSidebar }: { onToggleSidebar?: () => void } = $props();

  let os = $state("linux");

  $effect(() => {
    try {
      os = platform();
    } catch {
      os = "linux";
    }
  });

  const isMac = $derived(os === "macos");

  const headerClass = $derived(
    isMac
      ? "relative flex w-full shrink-0 items-center border-b border-border/50 h-[38px]"
      : os === "windows"
        ? "relative flex w-full shrink-0 items-center border-b border-border/50 h-[32px]"
        : "relative flex w-full shrink-0 items-center border-b border-border/50 h-[34px]",
  );

  const leftZoneClass = $derived(
    isMac ? "flex items-center pl-[76px]" : "flex items-center pl-2",
  );

  async function startDrag(e: MouseEvent) {
    const target = e.target as HTMLElement;
    if (target.closest("button") || target.closest("input")) return;
    try {
      await getCurrentWindow().startDragging();
    } catch {
      // not in Tauri context
    }
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<header
  class={headerClass}
  onmousedown={startDrag}
  data-tauri-drag-region
>
  <!-- Left zone: sidebar toggle (+ macOS traffic light inset) -->
  <div class={leftZoneClass}>
    {#if onToggleSidebar}
      <button
        onclick={onToggleSidebar}
        class="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors duration-100 hover:bg-foreground/10 hover:text-foreground @[pointer:coarse]:h-9 @[pointer:coarse]:w-9"
      >
        <PanelLeft class="h-4 w-4" strokeWidth={1.75} />
      </button>
    {/if}
  </div>

  <!-- Center zone: session title + model badge -->
  <div class="flex min-w-0 flex-1 items-center gap-2 px-2">
    <SessionTitle />
    <span class="text-muted-foreground/40">&middot;</span>
    <ModelBadge />
  </div>

  <!-- Right zone: quick actions + connection badge + window controls -->
  <div class="flex items-center gap-0.5 pr-0.5">
    <QuickActions />
    <ConnectionBadge />
    {#if !isMac}
      <WindowControls platform={os} />
    {/if}
  </div>

  <!-- Agent progress bar at bottom edge -->
  <AgentProgressBar />
</header>
