<script lang="ts">
  import { goto } from "$app/navigation";
  import { Check } from "@lucide/svelte";

  const suggestions = [
    "Summarize this PDF",
    "What can you help me with?",
    "Set a reminder for tomorrow",
  ];

  function startChatting(prefill?: string) {
    localStorage.setItem("pocketpaw_onboarded", "true");
    if (prefill) {
      localStorage.setItem("pocketpaw_prefill", prefill);
    }
    goto("/");
  }
</script>

<div class="flex flex-col items-center gap-6 text-center">
  <div class="flex h-12 w-12 items-center justify-center rounded-full bg-paw-success/10">
    <Check class="h-6 w-6 text-paw-success" strokeWidth={2} />
  </div>

  <div class="flex flex-col gap-2">
    <h1 class="text-2xl font-semibold text-foreground">You're all set!</h1>
    <p class="text-sm text-muted-foreground">Try saying:</p>
  </div>

  <div class="flex flex-col gap-2">
    {#each suggestions as text}
      <button
        onclick={() => startChatting(text)}
        class="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:bg-accent hover:text-foreground"
      >
        "{text}"
      </button>
    {/each}
  </div>

  <button
    onclick={() => startChatting()}
    class="mt-2 rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
  >
    Start Chatting
  </button>
</div>
