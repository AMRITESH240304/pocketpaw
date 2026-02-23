<script lang="ts">
  import type { BackendInfo, Settings } from "$lib/api";
  import { connectionStore, settingsStore } from "$lib/stores";
  import * as Select from "$lib/components/ui/select";
  import { Switch } from "$lib/components/ui/switch";
  import { Eye, EyeOff, Loader2, Download } from "@lucide/svelte";
  import { toast } from "svelte-sonner";

  let backends = $state<BackendInfo[]>([]);
  let loading = $state(true);
  let saving = $state(false);
  let installing = $state<string | null>(null);

  // Local form state
  let selectedBackend = $state("");
  let selectedProvider = $state("");
  let selectedModel = $state("");
  let customModel = $state("");
  let ollamaHost = $state("http://localhost:11434");
  let apiKeyInput = $state("");
  let apiKeyMasked = $state(true);
  let changingKey = $state(false);
  let smartRouting = $state(false);
  let maxTurns = $state(25);

  // Known models per provider
  const PROVIDER_MODELS: Record<string, string[]> = {
    anthropic: ["claude-sonnet-4-5-20250514", "claude-opus-4-5-20250414", "claude-haiku-4-5-20251001"],
    openai: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview"],
    google: ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-pro"],
    ollama: ["llama3.2", "mistral", "codellama", "gemma2", "phi3"],
  };

  // Per-backend field mapping
  type BackendFields = {
    providerField?: keyof Settings;
    modelField: keyof Settings;
    maxTurnsField: keyof Settings;
  };

  const BACKEND_FIELDS: Record<string, BackendFields> = {
    claude_agent_sdk: { providerField: "claude_sdk_provider", modelField: "claude_sdk_model", maxTurnsField: "claude_sdk_max_turns" },
    openai_agents: { providerField: "openai_agents_provider", modelField: "openai_agents_model", maxTurnsField: "openai_agents_max_turns" },
    google_adk: { modelField: "google_adk_model", maxTurnsField: "google_adk_max_turns" },
    codex_cli: { modelField: "codex_cli_model", maxTurnsField: "codex_cli_max_turns" },
    copilot_sdk: { providerField: "copilot_sdk_provider", modelField: "copilot_sdk_model", maxTurnsField: "copilot_sdk_max_turns" },
    opencode: { modelField: "opencode_model", maxTurnsField: "opencode_max_turns" },
  };

  let currentBackend = $derived(backends.find((b) => b.name === selectedBackend));
  let providers = $derived(currentBackend?.supportedProviders ?? []);
  let models = $derived(PROVIDER_MODELS[selectedProvider] ?? []);
  let effectiveModel = $derived(customModel || selectedModel);

  function syncFromSettings(s: Settings | null) {
    if (!s) return;
    selectedBackend = s.agent_backend ?? "";
    smartRouting = s.smart_routing_enabled ?? false;
    ollamaHost = (s.ollama_host as string) ?? "http://localhost:11434";

    const fields = BACKEND_FIELDS[s.agent_backend];
    if (fields) {
      selectedProvider = fields.providerField ? (s[fields.providerField] as string) ?? "" : "";
      const model = (s[fields.modelField] as string) ?? "";
      selectedModel = model;
      customModel = "";
      maxTurns = (s[fields.maxTurnsField] as number) ?? 25;
    } else {
      selectedProvider = "";
      selectedModel = "";
      customModel = "";
      maxTurns = 25;
    }

    // Fallback: if no per-backend provider, check global
    if (!selectedProvider && s.llm_provider) {
      selectedProvider = s.llm_provider;
    }
  }

  $effect(() => {
    syncFromSettings(settingsStore.settings);
  });

  $effect(() => {
    loadBackends();
  });

  async function loadBackends() {
    try {
      const client = connectionStore.getClient();
      backends = await client.listBackends();
    } catch {
      // Backend not available — show empty
    } finally {
      loading = false;
    }
  }

  async function handleInstall(name: string) {
    installing = name;
    try {
      const client = connectionStore.getClient();
      await client.installBackend(name);
      toast.success(`Installing ${name}...`);
      // Reload backends after a short delay
      setTimeout(loadBackends, 3000);
    } catch {
      toast.error(`Failed to install ${name}`);
    } finally {
      installing = null;
    }
  }

  async function handleSave() {
    saving = true;
    try {
      const patch: Partial<Settings> = {
        agent_backend: selectedBackend,
        smart_routing_enabled: smartRouting,
      };

      const fields = BACKEND_FIELDS[selectedBackend];
      if (fields) {
        if (fields.providerField) {
          patch[fields.providerField] = selectedProvider;
        }
        patch[fields.modelField] = effectiveModel;
        patch[fields.maxTurnsField] = maxTurns;
      }

      // When provider is ollama, also save ollama-specific fields
      if (selectedProvider === "ollama") {
        patch.ollama_host = ollamaHost;
        patch.ollama_model = effectiveModel;
        patch.llm_provider = "ollama";
      }

      await settingsStore.update(patch);
      toast.success("Settings saved");
    } catch {
      toast.error("Failed to save settings");
    } finally {
      saving = false;
    }
  }

  function handleSaveApiKey() {
    if (!apiKeyInput.trim()) return;
    settingsStore.saveApiKey(selectedProvider, apiKeyInput.trim());
    apiKeyInput = "";
    changingKey = false;
    toast.success("API key saved");
  }
</script>

<div class="flex flex-col gap-6">
  <h3 class="text-sm font-semibold text-foreground">AI Model</h3>

  {#if loading}
    <div class="flex items-center gap-2 py-4 text-sm text-muted-foreground">
      <Loader2 class="h-4 w-4 animate-spin" />
      Loading backends...
    </div>
  {:else}
    <!-- Backend -->
    <div class="flex flex-col gap-1.5">
      <span class="text-xs font-medium text-muted-foreground">Backend</span>
      <Select.Root type="single" bind:value={selectedBackend}>
        <Select.Trigger class="w-full">
          {selectedBackend
            ? (backends.find((b) => b.name === selectedBackend)?.displayName ?? selectedBackend)
            : "Select backend..."}
        </Select.Trigger>
        <Select.Content>
          {#each backends as backend (backend.name)}
            {#if backend.available}
              <Select.Item value={backend.name} label={backend.displayName} />
            {/if}
          {/each}
          {#if backends.filter((b) => b.available).length === 0}
            <div class="px-2 py-1.5 text-xs text-muted-foreground">No backends available</div>
          {/if}
        </Select.Content>
      </Select.Root>
    </div>

    <!-- Unavailable backends — install buttons -->
    {#if backends.filter((b) => !b.available).length > 0}
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium text-muted-foreground">Install Additional Backends</span>
        <div class="flex flex-wrap gap-2">
          {#each backends.filter((b) => !b.available) as backend (backend.name)}
            <button
              onclick={() => handleInstall(backend.name)}
              disabled={installing === backend.name}
              class="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground disabled:opacity-40"
            >
              {#if installing === backend.name}
                <Loader2 class="h-3 w-3 animate-spin" />
              {:else}
                <Download class="h-3 w-3" />
              {/if}
              {backend.displayName}
              {#if backend.beta}
                <span class="text-[10px] text-muted-foreground/60">(beta)</span>
              {/if}
            </button>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Provider -->
    {#if providers.length > 0}
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium text-muted-foreground">Provider</span>
        <Select.Root type="single" bind:value={selectedProvider}>
          <Select.Trigger class="w-full">
            {selectedProvider || "Select provider..."}
          </Select.Trigger>
          <Select.Content>
            {#each providers as p (p)}
              <Select.Item value={p} label={p.charAt(0).toUpperCase() + p.slice(1)} />
            {/each}
          </Select.Content>
        </Select.Root>
      </div>
    {/if}

    <!-- Ollama Host -->
    {#if selectedProvider === "ollama"}
      <div class="flex flex-col gap-1.5">
        <label for="ollama-host" class="text-xs font-medium text-muted-foreground">Ollama Host</label>
        <input
          id="ollama-host"
          bind:value={ollamaHost}
          type="text"
          placeholder="http://localhost:11434"
          class="h-9 w-full rounded-lg border border-border bg-muted/50 px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
        />
      </div>
    {/if}

    <!-- API Key -->
    {#if selectedProvider && selectedProvider !== "ollama"}
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium text-muted-foreground">API Key</span>
        {#if changingKey}
          <div class="flex gap-2">
            <div class="relative flex-1">
              <input
                bind:value={apiKeyInput}
                type={apiKeyMasked ? "password" : "text"}
                placeholder="Enter API key..."
                class="h-9 w-full rounded-lg border border-border bg-muted/50 px-3 pr-9 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
              />
              <button
                onclick={() => (apiKeyMasked = !apiKeyMasked)}
                class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
              >
                {#if apiKeyMasked}
                  <Eye class="h-3.5 w-3.5" />
                {:else}
                  <EyeOff class="h-3.5 w-3.5" />
                {/if}
              </button>
            </div>
            <button
              onclick={handleSaveApiKey}
              disabled={!apiKeyInput.trim()}
              class="rounded-lg bg-primary px-3 py-2 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              Save
            </button>
            <button
              onclick={() => { changingKey = false; apiKeyInput = ""; }}
              class="rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              Cancel
            </button>
          </div>
          <p class="text-[10px] text-muted-foreground">Encrypted and stored locally</p>
        {:else}
          <div class="flex items-center gap-2">
            <span class="text-sm text-muted-foreground">sk-•••••••••••••</span>
            <button
              onclick={() => (changingKey = true)}
              class="text-xs text-primary transition-opacity hover:opacity-80"
            >
              Change
            </button>
          </div>
        {/if}
      </div>
    {/if}

    <!-- Model -->
    {#if selectedProvider || selectedBackend}
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium text-muted-foreground">Model</span>
        {#if models.length > 0}
          <Select.Root type="single" bind:value={selectedModel}>
            <Select.Trigger class="w-full">
              {selectedModel || "Select model..."}
            </Select.Trigger>
            <Select.Content>
              {#each models as m (m)}
                <Select.Item value={m} label={m} />
              {/each}
            </Select.Content>
          </Select.Root>
        {/if}
        <input
          bind:value={customModel}
          type="text"
          placeholder={models.length > 0 ? "Or type a custom model name..." : "Enter model name..."}
          class="h-9 w-full rounded-lg border border-border bg-muted/50 px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
        />
        {#if customModel}
          <p class="text-[10px] text-muted-foreground">
            Custom model overrides dropdown selection
          </p>
        {/if}
      </div>
    {/if}

    <!-- Separator -->
    {#if selectedProvider !== "ollama"}
      <div class="border-t border-border/50"></div>
      <div class="flex flex-col gap-1.5">
        <p class="text-xs text-muted-foreground">Or use a free local model:</p>
        <button
          onclick={() => { selectedProvider = "ollama"; selectedModel = ""; customModel = ""; }}
          class="w-fit rounded-lg border border-border px-4 py-2 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
        >
          Switch to Ollama (free, offline)
        </button>
      </div>
    {/if}

    <!-- Advanced -->
    <div class="border-t border-border/50"></div>
    <p class="text-xs font-medium text-muted-foreground">Advanced</p>

    <div class="flex items-center justify-between">
      <div class="flex flex-col">
        <span class="text-sm text-foreground">Smart Routing</span>
        <span class="text-[10px] text-muted-foreground">Routes simple queries to cheaper models</span>
      </div>
      <Switch bind:checked={smartRouting} />
    </div>

    <div class="flex flex-col gap-1.5">
      <label for="max-turns" class="text-xs font-medium text-muted-foreground">Max Turns</label>
      <input
        id="max-turns"
        bind:value={maxTurns}
        type="number"
        min={1}
        max={100}
        class="h-9 w-24 rounded-lg border border-border bg-muted/50 px-3 text-sm text-foreground focus:border-primary focus:outline-none"
      />
    </div>

    <!-- Save button -->
    <div class="flex justify-end pt-2">
      <button
        onclick={handleSave}
        disabled={saving}
        class="rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
      >
        {#if saving}
          Saving...
        {:else}
          Save
        {/if}
      </button>
    </div>
  {/if}
</div>
