<script lang="ts">
  import { chatStore } from "$lib/stores";
  import { Square } from "@lucide/svelte";
  import MarkdownRenderer from "./MarkdownRenderer.svelte";

  let streamingContent = $derived(chatStore.streamingContent);
  let hasContent = $derived(streamingContent.length > 0);

  function stop() {
    chatStore.stopGeneration();
  }
</script>

<div class="flex flex-col gap-1">
  <div class="flex items-center gap-2">
    <span class="text-sm">🐾</span>
    <span class="text-xs font-medium text-muted-foreground">PocketPaw</span>
  </div>

  <div class="max-w-full pl-6">
    {#if hasContent}
      <div class="text-sm leading-relaxed text-foreground">
        <MarkdownRenderer content={streamingContent} />
        <span class="animate-cursor-blink ml-0.5 inline-block h-4 w-[2px] translate-y-[2px] bg-foreground"></span>
      </div>
    {:else}
      <div class="flex items-center gap-2">
        <div class="flex gap-1">
          <div class="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" style="animation-delay: 0ms"></div>
          <div class="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" style="animation-delay: 150ms"></div>
          <div class="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" style="animation-delay: 300ms"></div>
        </div>
        <span class="text-xs text-muted-foreground">Thinking...</span>
      </div>
    {/if}

    <button
      onclick={stop}
      class="mt-2 inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      <Square class="h-3 w-3" fill="currentColor" />
      Stop generating
    </button>
  </div>
</div>
