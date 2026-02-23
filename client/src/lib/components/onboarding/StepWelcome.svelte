<script lang="ts">
  let { onNext }: { onNext: () => void } = $props();
</script>

<div class="flex flex-col items-center gap-6 text-center">
  <span class="text-5xl">🐾</span>

  <div class="flex flex-col gap-2">
    <h1 class="text-2xl font-semibold text-foreground">Welcome to PocketPaw</h1>
    <p class="max-w-sm text-sm text-muted-foreground">
      Your AI that runs on your machine. Private. Secure. Yours.
    </p>
  </div>

  <button
    onclick={onNext}
    class="mt-4 rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
  >
    Get Started
  </button>
</div>
