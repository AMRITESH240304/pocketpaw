<script lang="ts">
  import { File, Image, FileText, FileCode, X } from "@lucide/svelte";
  import type { MediaAttachment } from "$lib/api";

  let {
    file,
    removable = false,
    onRemove,
  }: {
    file: MediaAttachment | { name: string; type: string; size?: number };
    removable?: boolean;
    onRemove?: () => void;
  } = $props();

  let fileName = $derived("name" in file ? file.name : "file");
  let fileType = $derived("type" in file ? file.type : "");

  let Icon = $derived.by(() => {
    if (fileType.startsWith("image/")) return Image;
    if (fileType.includes("pdf")) return FileText;
    if (fileType.includes("code") || fileType.includes("javascript") || fileType.includes("typescript") || fileType.includes("json")) return FileCode;
    return File;
  });

  function formatSize(bytes?: number): string {
    if (!bytes) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  let sizeStr = $derived("size" in file ? formatSize(file.size as number) : "");
</script>

<div class="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-1 text-xs">
  <Icon class="h-3 w-3 shrink-0 text-muted-foreground" strokeWidth={2} />
  <span class="max-w-[120px] truncate text-foreground">{fileName}</span>
  {#if sizeStr}
    <span class="text-muted-foreground">{sizeStr}</span>
  {/if}
  {#if removable && onRemove}
    <button
      onclick={onRemove}
      class="ml-0.5 rounded-sm p-0.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      <X class="h-3 w-3" />
    </button>
  {/if}
</div>
