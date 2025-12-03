<script setup>
defineProps({
  serviceOnline: { type: Boolean, default: false },
  isHistoryView: { type: Boolean, default: false },
  apiBaseUrl: { type: String, default: '' },
  loadError: { type: String, default: '' },
  availableModeCount: { type: Number, default: 0 },
  lastDuration: { type: String, default: '--' },
  lastRunAt: { type: String, default: '--' },
})
</script>

<template>
  <header class="hero">
    <div>
      <p class="eyebrow">DeepSeek OCR 控制台</p>
      <h1>本地 DeepSeek-OCR 推理</h1>
      <p class="subtitle">
        上传图片、选择模式，即可通过 FastAPI 网关触发 DeepSeek-OCR，本地 GPU 一次加载，多次复用。
      </p>
      <div class="status-row">
        <span class="status-pill" :class="serviceOnline ? 'online' : 'offline'">
          {{ serviceOnline ? '推理服务运行中' : '推理服务离线' }}
        </span>
        <span class="status-pill light" v-if="isHistoryView">历史记录浏览</span>
        <span class="status-pill light">API {{ apiBaseUrl }}</span>
        <span class="status-pill light" v-if="loadError">{{ loadError }}</span>
      </div>
    </div>
    <ul class="hero-metrics">
      <li>
        <span>可选模式</span>
        <strong>{{ availableModeCount || '--' }}</strong>
      </li>
      <li>
        <span>最近推理耗时</span>
        <strong>{{ lastDuration }}</strong>
      </li>
      <li>
        <span>最近推理时间</span>
        <strong>{{ lastRunAt || '--' }}</strong>
      </li>
    </ul>
  </header>
</template>
