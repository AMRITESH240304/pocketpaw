<script lang="ts">
  import { onMount } from "svelte";
  import ChatPanel from "$lib/components/chat/ChatPanel.svelte";

  let prefill = $state("");

  onMount(() => {
    const stored = localStorage.getItem("pocketpaw_prefill");
    if (stored) {
      prefill = stored;
      localStorage.removeItem("pocketpaw_prefill");
    }
  });
</script>

<ChatPanel initialValue={prefill} />
