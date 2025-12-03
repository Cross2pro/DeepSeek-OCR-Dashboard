<script setup>
defineProps({
  inferenceResult: {
    type: Object,
    default: null,
  },
  availableModes: {
    type: Object,
    default: () => ({}),
  },
  formatBytes: {
    type: Function,
    default: () => '',
  },
})
</script>

<template>
  <article class="card meta-card" v-if="inferenceResult">
    <h2>推理详情</h2>
    <ul>
      <li>
        <span>模式</span>
        <strong>{{ availableModes[inferenceResult.mode]?.label || inferenceResult.mode }}</strong>
      </li>
      <li>
        <span>耗时</span>
        <strong>{{ inferenceResult.durationMs.toFixed(0) }} ms</strong>
      </li>
      <li>
        <span>文件</span>
        <strong>{{ inferenceResult.fileName }} · {{ formatBytes(inferenceResult.fileSize) }}</strong>
      </li>
      <li>
        <span>提示词</span>
        <strong>{{ inferenceResult.prompt }}</strong>
      </li>
    </ul>
  </article>
</template>
