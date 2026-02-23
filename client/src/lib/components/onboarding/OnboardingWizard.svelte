<script lang="ts">
  import StepWelcome from "./StepWelcome.svelte";
  import StepChooseAI from "./StepChooseAI.svelte";
  import StepReady from "./StepReady.svelte";

  let currentStep = $state(1);

  function next() {
    currentStep++;
  }
</script>

<div class="flex h-full w-full flex-col items-center justify-center px-6">
  <!-- Step indicator -->
  <div class="mb-8 flex items-center gap-2">
    {#each [1, 2, 3] as step}
      <div
        class={step === currentStep
          ? "h-1.5 w-6 rounded-full bg-primary"
          : step < currentStep
            ? "h-1.5 w-6 rounded-full bg-primary/40"
            : "h-1.5 w-6 rounded-full bg-muted"}
      ></div>
    {/each}
  </div>

  <!-- Step content -->
  {#if currentStep === 1}
    <StepWelcome onNext={next} />
  {:else if currentStep === 2}
    <StepChooseAI onNext={next} />
  {:else if currentStep === 3}
    <StepReady />
  {/if}
</div>
