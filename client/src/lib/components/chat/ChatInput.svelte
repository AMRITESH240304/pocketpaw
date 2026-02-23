<script lang="ts">
  import { chatStore, connectionStore, settingsStore, skillStore } from "$lib/stores";
  import { X, Plus, ArrowUp, Globe, Brain, Wrench, Search } from "@lucide/svelte";
  import * as InputGroup from "$lib/components/ui/input-group";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { Separator } from "$lib/components/ui/separator";
  import FilePreview from "./FilePreview.svelte";

  let { initialValue = "" }: { initialValue?: string } = $props();

  let inputValue = $state("");
  let textareaEl: HTMLTextAreaElement | null = $state(null);
  let attachedFiles = $state<{ name: string; type: string; size: number; file: File }[]>([]);
  let isDragOver = $state(false);

  // Sync initialValue prop into state
  $effect(() => {
    if (initialValue) {
      inputValue = initialValue;
    }
  });

  let isStreaming = $derived(chatStore.isStreaming);
  let isConnected = $derived(connectionStore.isConnected);
  let canSend = $derived(
    (inputValue.trim().length > 0 || attachedFiles.length > 0) && !isStreaming && isConnected,
  );

  // Active model display — short name from settings
  let activeModel = $derived.by(() => {
    const m = settingsStore.model;
    if (!m) return "";
    // Shorten common model names: "claude-sonnet-4-..." → "Sonnet 4"
    if (m.includes("sonnet")) return "Sonnet";
    if (m.includes("opus")) return "Opus";
    if (m.includes("haiku")) return "Haiku";
    if (m.includes("gpt-4o")) return "GPT-4o";
    if (m.includes("gpt-4")) return "GPT-4";
    if (m.includes("o3")) return "o3";
    if (m.includes("o1")) return "o1";
    if (m.includes("gemini")) return "Gemini";
    // Fallback: last segment after last slash or dash, capped
    const short = m.split(/[/-]/).pop() ?? m;
    return short.length > 12 ? short.slice(0, 12) : short;
  });

  let activeBackend = $derived(settingsStore.agentBackend);
  let skillCount = $derived(skillStore.skills.length);
  let planMode = $derived(settingsStore.settings?.plan_mode ?? false);
  let webSearch = $derived(settingsStore.settings?.smart_routing_enabled ?? false);

  function handleSubmit() {
    const text = inputValue.trim();
    if (!text && attachedFiles.length === 0) return;
    if (isStreaming) return;

    const media: import("$lib/api").MediaAttachment[] = attachedFiles.map((f) => ({
      type: "file" as const,
      filename: f.name,
      mime_type: f.type,
    }));

    chatStore.sendMessage(text || "(files attached)", media.length > 0 ? media : undefined);
    inputValue = "";
    attachedFiles = [];
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function openFilePicker() {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.accept = "image/*,.pdf,.txt,.md,.csv,.json,.js,.ts,.py,.html,.css";
    input.onchange = () => {
      if (input.files) {
        addFiles(Array.from(input.files));
      }
    };
    input.click();
  }

  function addFiles(files: File[]) {
    for (const file of files) {
      if (attachedFiles.length >= 10) break;
      attachedFiles.push({
        name: file.name,
        type: file.type || "application/octet-stream",
        size: file.size,
        file,
      });
    }
    attachedFiles = attachedFiles;
  }

  function removeFile(index: number) {
    attachedFiles = attachedFiles.filter((_, i) => i !== index);
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    isDragOver = true;
  }

  function handleDragLeave() {
    isDragOver = false;
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    isDragOver = false;
    if (e.dataTransfer?.files) {
      addFiles(Array.from(e.dataTransfer.files));
    }
  }

  function stopGeneration() {
    chatStore.stopGeneration();
  }

  async function togglePlanMode() {
    const next = !planMode;
    try {
      await settingsStore.update({ plan_mode: next });
    } catch {
      // Failed to update
    }
  }

  async function toggleWebSearch() {
    const next = !webSearch;
    try {
      await settingsStore.update({ smart_routing_enabled: next });
    } catch {
      // Failed to update
    }
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class={isDragOver
    ? "border-t-2 border-primary bg-paw-accent-subtle px-4 py-3"
    : "px-4 py-3 "}
  ondragover={handleDragOver}
  ondragleave={handleDragLeave}
  ondrop={handleDrop}
>
  {#if isDragOver}
    <div class="flex items-center justify-center py-4">
      <p class="text-sm font-medium text-primary">Drop files here</p>
    </div>
  {:else}
    <div class="mx-auto max-w-3xl">
      <!-- Attached files -->
      {#if attachedFiles.length > 0}
        <div class="mb-2 flex flex-wrap gap-1.5">
          {#each attachedFiles as file, i}
            <FilePreview
              file={{ name: file.name, type: file.type, size: file.size }}
              removable
              onRemove={() => removeFile(i)}
            />
          {/each}
        </div>
      {/if}

      <InputGroup.Root>
        <InputGroup.Textarea
          bind:ref={textareaEl}
          bind:value={inputValue}
          onkeydown={handleKeydown}
          placeholder={isConnected ? "Ask, search, or run a skill..." : "Connecting..."}
          disabled={!isConnected}
        />
        <InputGroup.Addon align="block-end">
          <InputGroup.Button
            variant="outline"
            class="rounded-full"
            size="icon-xs"
            onclick={openFilePicker}
            disabled={isStreaming}
          >
            <Plus />
          </InputGroup.Button>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>
              {#snippet child({ props })}
                <InputGroup.Button {...props} variant="ghost">
                  <Brain class="mr-1 h-3 w-3" />
                  {#if planMode}Plan{:else}Chat{/if}
                </InputGroup.Button>
              {/snippet}
            </DropdownMenu.Trigger>
            <DropdownMenu.Content side="top" align="start" class="[--radius:0.95rem]">
              <DropdownMenu.Item onclick={togglePlanMode}>
                <Brain class="mr-2 h-3.5 w-3.5" />
                {planMode ? "Disable" : "Enable"} Plan Mode
              </DropdownMenu.Item>
              <DropdownMenu.Item onclick={toggleWebSearch}>
                <Search class="mr-2 h-3.5 w-3.5" />
                {webSearch ? "Disable" : "Enable"} Smart Routing
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
          <div class="ms-auto flex items-center gap-1">
            {#if activeModel}
              <InputGroup.Text class="text-muted-foreground">
                {activeModel}
              </InputGroup.Text>
            {/if}
            {#if skillCount > 0}
              <InputGroup.Text class="text-muted-foreground">
                <Wrench class="mr-0.5 h-3 w-3" />
                {skillCount}
              </InputGroup.Text>
            {/if}
          </div>
          <Separator orientation="vertical" class="!h-4" />
          {#if isStreaming}
            <InputGroup.Button
              variant="outline"
              class="rounded-full"
              size="icon-xs"
              onclick={stopGeneration}
            >
              <X />
              <span class="sr-only">Stop</span>
            </InputGroup.Button>
          {:else}
            <InputGroup.Button
              variant="default"
              class="rounded-full"
              size="icon-xs"
              disabled={!canSend}
              onclick={handleSubmit}
            >
              <ArrowUp />
              <span class="sr-only">Send</span>
            </InputGroup.Button>
          {/if}
        </InputGroup.Addon>
      </InputGroup.Root>
    </div>
  {/if}
</div>
