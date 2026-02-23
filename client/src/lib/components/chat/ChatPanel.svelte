<script lang="ts">
  import { chatStore } from "$lib/stores";
  import { AlertCircle, X } from "@lucide/svelte";
  import MessageList from "./MessageList.svelte";
  import ChatInput from "./ChatInput.svelte";
  import EmptyState from "./EmptyState.svelte";

  let { initialValue = "" }: { initialValue?: string } = $props();

  let isEmpty = $derived(chatStore.isEmpty && !chatStore.isStreaming);
  let error = $derived(chatStore.error);

  function handleSuggestion(text: string) {
    chatStore.sendMessage(text);
  }

  function dismissError() {
    chatStore.error = null;
  }
</script>

<div class="flex h-full flex-col">
  {#if isEmpty}
    <div class="flex flex-1 items-center justify-center">
      <EmptyState onSuggestionClick={handleSuggestion} />
    </div>
  {:else}
    <MessageList />
  {/if}

  {#if error}
    <div class="mx-4 mb-2 flex items-center gap-2 rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-400">
      <AlertCircle class="h-4 w-4 shrink-0" />
      <span class="flex-1">{error}</span>
      <button onclick={dismissError} class="shrink-0 rounded-sm p-0.5 transition-colors hover:bg-red-500/20">
        <X class="h-3.5 w-3.5" />
      </button>
    </div>
  {/if}

  <ChatInput {initialValue} />
</div>
