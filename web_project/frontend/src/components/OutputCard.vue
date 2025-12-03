<script setup>
defineProps({
  inferenceResult: {
    type: Object,
    default: null,
  },
  isRunning: {
    type: Boolean,
    default: false,
  },
  downloadMarkdown: Function,
  copyOutput: Function,
})
</script>

<template>
  <article class="card output-card">
    <div class="card-header">
      <div>
        <h2>推理输出</h2>
        <p>DeepSeek-OCR 将解析结构化文本。</p>
      </div>
      <div class="output-actions">
        <button type="button" class="ghost" :disabled="!inferenceResult?.text" @click="downloadMarkdown">
          下载
        </button>
        <button type="button" class="ghost" :disabled="!inferenceResult?.text" @click="copyOutput">
          复制
        </button>
      </div>
    </div>
    <div class="output-body" :class="{ loading: isRunning }">
      <p v-if="isRunning" class="muted">推理进行中，请稍候...</p>
      <p v-else-if="!inferenceResult" class="muted">等待推理结果...</p>
      <pre v-else>{{ inferenceResult.text }}</pre>
    </div>
  </article>
</template>
