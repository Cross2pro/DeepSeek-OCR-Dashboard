<script setup>
defineProps({
  steps: {
    type: Array,
    default: () => [],
  },
})
</script>

<template>
  <article class="card step-card">
    <h2>流程</h2>
    <div class="steps">
      <div v-for="step in steps" :key="step.key" class="step" :class="step.status">
        <div class="step-index">
          <span></span>
        </div>
        <div>
          <p>{{ step.label }}</p>
          <small>{{ step.description }}</small>
        </div>
      </div>
    </div>
  </article>
</template>
