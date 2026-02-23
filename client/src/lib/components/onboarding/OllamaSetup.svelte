<script lang="ts">
  import { settingsStore } from "$lib/stores";
  import { Loader2, RefreshCw, ExternalLink, Check } from "@lucide/svelte";
  import { Progress } from "$lib/components/ui/progress";

  let { onComplete, onBack }: { onComplete: () => void; onBack: () => void } = $props();

  type OllamaModel = { name: string; size: number };

  let status = $state<"checking" | "not_found" | "found" | "pulling" | "done">("checking");
  let models = $state<OllamaModel[]>([]);
  let selectedModel = $state("llama3.2");
  let pullProgress = $state(0);
  let error = $state("");

  const defaultModels = [
    { id: "llama3.2", name: "Llama 3.2", desc: "Fast, versatile, 3B params" },
    { id: "llama3.2:1b", name: "Llama 3.2 1B", desc: "Lightweight, fastest" },
    { id: "mistral", name: "Mistral 7B", desc: "Strong reasoning" },
    { id: "gemma2:2b", name: "Gemma 2 2B", desc: "Google, compact" },
  ];

  async function checkOllama() {
    status = "checking";
    error = "";
    try {
      const res = await fetch("http://localhost:11434/api/tags");
      if (res.ok) {
        const data = await res.json();
        models = data.models ?? [];
        status = "found";
      } else {
        status = "not_found";
      }
    } catch {
      status = "not_found";
    }
  }

  async function pullModel() {
    status = "pulling";
    pullProgress = 0;
    error = "";

    try {
      const res = await fetch("http://localhost:11434/api/pull", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: selectedModel }),
      });

      if (!res.ok || !res.body) {
        error = "Failed to start model download";
        status = "found";
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value, { stream: true }).split("\n");
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line);
            if (data.total && data.completed) {
              pullProgress = Math.round((data.completed / data.total) * 100);
            }
            if (data.status === "success") {
              pullProgress = 100;
            }
          } catch {
            // skip
          }
        }
      }

      status = "done";
      saveAndContinue();
    } catch (e) {
      error = "Download failed. Check that Ollama is running.";
      status = "found";
    }
  }

  function saveAndContinue() {
    settingsStore.update({
      agent_backend: "claude_agent_sdk",
      llm_provider: "ollama",
      ollama_model: selectedModel,
    });
    onComplete();
  }

  function selectExistingModel(name: string) {
    selectedModel = name;
    saveAndContinue();
  }

  // Check on mount
  $effect(() => {
    checkOllama();
  });

  let hasExistingModels = $derived(models.length > 0);
</script>

<div class="flex w-full max-w-md flex-col gap-5">
  <button
    onclick={onBack}
    class="self-start text-xs text-muted-foreground transition-colors hover:text-foreground"
  >
    &larr; Back
  </button>

  <div class="flex flex-col gap-1">
    <h2 class="text-lg font-semibold text-foreground">Set Up Local AI</h2>
    <p class="text-sm text-muted-foreground">
      PocketPaw uses Ollama to run AI models on your machine.
    </p>
  </div>

  {#if status === "checking"}
    <div class="flex items-center gap-2 rounded-lg border border-border bg-muted/50 p-4">
      <Loader2 class="h-4 w-4 animate-spin text-muted-foreground" />
      <span class="text-sm text-muted-foreground">Looking for Ollama...</span>
    </div>
  {:else if status === "not_found"}
    <div class="flex flex-col gap-3 rounded-lg border border-border bg-muted/50 p-4">
      <p class="text-sm text-foreground">Ollama is not running on this machine.</p>
      <p class="text-sm text-muted-foreground">
        Install Ollama to run AI models locally, for free.
      </p>
      <div class="flex items-center gap-2">
        <a
          href="https://ollama.ai/download"
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          Download Ollama
          <ExternalLink class="h-3 w-3" />
        </a>
        <button
          onclick={checkOllama}
          class="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <RefreshCw class="h-3 w-3" />
          Check Again
        </button>
      </div>
    </div>
  {:else if status === "found"}
    <div class="flex flex-col gap-3">
      {#if hasExistingModels}
        <div class="flex flex-col gap-1.5">
          <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
            Installed Models
          </p>
          {#each models as model}
            <button
              onclick={() => selectExistingModel(model.name)}
              class="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-left text-sm transition-colors hover:bg-accent"
            >
              <span class="font-medium text-foreground">{model.name}</span>
              <span class="text-xs text-muted-foreground">
                {Math.round(model.size / 1e9 * 10) / 10} GB
              </span>
            </button>
          {/each}
        </div>
      {/if}

      <div class="flex flex-col gap-1.5">
        <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
          {hasExistingModels ? "Or download a model" : "Choose a model to download"}
        </p>
        {#each defaultModels as model}
          <button
            onclick={() => { selectedModel = model.id; pullModel(); }}
            class="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-left text-sm transition-colors hover:bg-accent"
          >
            <div>
              <span class="font-medium text-foreground">{model.name}</span>
              <span class="ml-2 text-xs text-muted-foreground">{model.desc}</span>
            </div>
          </button>
        {/each}
      </div>
    </div>
  {:else if status === "pulling"}
    <div class="flex flex-col gap-3 rounded-lg border border-border bg-muted/50 p-4">
      <div class="flex items-center gap-2">
        <Loader2 class="h-4 w-4 animate-spin text-primary" />
        <span class="text-sm text-foreground">
          Downloading {selectedModel}...
        </span>
      </div>
      <Progress value={pullProgress} max={100} class="h-2" />
      <p class="text-xs text-muted-foreground">{pullProgress}% complete</p>
    </div>
  {:else if status === "done"}
    <div class="flex items-center gap-2 rounded-lg border border-paw-success/30 bg-paw-success/10 p-4">
      <Check class="h-4 w-4 text-paw-success" />
      <span class="text-sm text-foreground">Model ready!</span>
    </div>
  {/if}

  {#if error}
    <p class="text-xs text-paw-error">{error}</p>
  {/if}
</div>
