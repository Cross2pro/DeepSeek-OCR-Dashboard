<script setup>
defineProps({
  canRun: Boolean,
  isRunning: Boolean,
  runInference: Function,
  hint: {
    type: String,
    default: '推理会占用 GPU，请确保已经按 requirements 安装依赖并加载模型。',
  },
  errorMessage: {
    type: String,
    default: '',
  },
  isHistoryView: Boolean,
  progressInfo: {
    type: Object,
    default: () => ({}),
  },
  getStageLabel: {
    type: Function,
    default: (stage) => stage,
  },
})
</script>

<template>
  <article class="card action-card">
    <div class="action-content">
      <button class="primary" type="button" :disabled="!canRun" @click="runInference">
        {{ isRunning ? '推理中 ...' : '开始推理' }}
      </button>
      <p class="hint">
        {{ hint }}
      </p>
      <p v-if="isHistoryView" class="hint">当前处于历史查看模式，上传新文件以重新推理。</p>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </div>

    <div v-if="isRunning || progressInfo.stage === 'complete'" class="progress-section">
      <div class="progress-header">
        <span class="progress-stage" :class="progressInfo.stage">
          {{ getStageLabel(progressInfo.stage) }}
        </span>
        <span class="progress-percent">{{ progressInfo.percent }}%</span>
      </div>
      <div class="progress-bar-container">
        <div 
          class="progress-bar-fill" 
          :class="progressInfo.stage"
          :style="{ width: progressInfo.percent + '%' }"
        ></div>
      </div>
      <p class="progress-message">{{ progressInfo.message }}</p>
    </div>
  </article>
</template>
