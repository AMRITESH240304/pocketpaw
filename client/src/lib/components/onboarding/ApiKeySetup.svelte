<script lang="ts">
  import { settingsStore } from "$lib/stores";
  import { ExternalLink, Eye, EyeOff, Shield } from "@lucide/svelte";

  let { onComplete, onBack }: { onComplete: () => void; onBack: () => void } = $props();

  const providers = [
    {
      id: "anthropic",
      name: "Anthropic (Claude)",
      prefix: "sk-ant-",
      keyUrl: "https://console.anthropic.com/settings/keys",
    },
    {
      id: "openai",
      name: "OpenAI",
      prefix: "sk-",
      keyUrl: "https://platform.openai.com/api-keys",
    },
    {
      id: "google",
      name: "Google (Gemini)",
      prefix: "AI",
      keyUrl: "https://aistudio.google.com/app/apikey",
    },
  ] as const;

  let selectedProvider = $state<(typeof providers)[number]["id"]>("anthropic");
  let apiKey = $state("");
  let showKey = $state(false);
  let error = $state("");

  let currentProvider = $derived(providers.find((p) => p.id === selectedProvider)!);

  function validate(): boolean {
    const trimmed = apiKey.trim();
    if (!trimmed) {
      error = "Please enter your API key.";
      return false;
    }
    if (selectedProvider === "anthropic" && !trimmed.startsWith("sk-ant-")) {
      error = "Anthropic keys start with sk-ant-";
      return false;
    }
    if (selectedProvider === "openai" && !trimmed.startsWith("sk-")) {
      error = "OpenAI keys start with sk-";
      return false;
    }
    error = "";
    return true;
  }

  function handleSubmit() {
    if (!validate()) return;
    settingsStore.saveApiKey(selectedProvider, apiKey.trim());
    onComplete();
  }
</script>

<div class="flex w-full max-w-md flex-col gap-5">
  <button
    onclick={onBack}
    class="self-start text-xs text-muted-foreground transition-colors hover:text-foreground"
  >
    &larr; Back
  </button>

  <div class="flex flex-col gap-1">
    <h2 class="text-lg font-semibold text-foreground">Connect an AI Provider</h2>
    <p class="text-sm text-muted-foreground">
      Paste your API key to use a cloud AI model.
    </p>
  </div>

  <!-- Provider selector -->
  <div class="flex gap-2">
    {#each providers as provider}
      <button
        onclick={() => { selectedProvider = provider.id; apiKey = ""; error = ""; }}
        class={selectedProvider === provider.id
          ? "rounded-lg border-2 border-primary px-3 py-2 text-sm font-medium text-foreground"
          : "rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"}
      >
        {provider.name}
      </button>
    {/each}
  </div>

  <!-- API key input -->
  <div class="flex flex-col gap-2">
    <div class="relative">
      <input
        type={showKey ? "text" : "password"}
        bind:value={apiKey}
        placeholder="Paste your API key"
        class="w-full rounded-lg border border-border bg-muted/50 px-3 py-2.5 pr-10 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
      />
      <button
        onclick={() => showKey = !showKey}
        class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground transition-colors hover:text-foreground"
      >
        {#if showKey}
          <EyeOff class="h-4 w-4" />
        {:else}
          <Eye class="h-4 w-4" />
        {/if}
      </button>
    </div>

    {#if error}
      <p class="text-xs text-paw-error">{error}</p>
    {/if}

    <a
      href={currentProvider.keyUrl}
      target="_blank"
      rel="noopener noreferrer"
      class="inline-flex items-center gap-1 text-xs text-primary transition-opacity hover:opacity-80"
    >
      Where do I get one?
      <ExternalLink class="h-3 w-3" />
    </a>
  </div>

  <!-- Trust message -->
  <div class="flex items-start gap-2 rounded-lg bg-muted/30 px-3 py-2.5">
    <Shield class="mt-0.5 h-3.5 w-3.5 shrink-0 text-paw-success" />
    <p class="text-xs text-muted-foreground">
      Your key is encrypted and stored locally. We never see it.
    </p>
  </div>

  <!-- Submit -->
  <button
    onclick={handleSubmit}
    disabled={!apiKey.trim()}
    class="rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
  >
    Continue
  </button>
</div>
