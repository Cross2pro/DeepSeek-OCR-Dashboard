<script setup>
defineProps({
  historyItems: {
    type: Array,
    default: () => [],
  },
  historyError: {
    type: String,
    default: '',
  },
  isLoadingHistory: {
    type: Boolean,
    default: false,
  },
  fetchHistory: Function,
  selectedHistoryId: {
    type: String,
    default: '',
  },
  isRunning: {
    type: Boolean,
    default: false,
  },
  availableModes: {
    type: Object,
    default: () => ({}),
  },
  loadHistory: Function,
})
</script>

<template>
  <article class="card history-card">
    <div class="card-header">
      <div>
        <h2>历史记录</h2>
        <p>缓存最近的推理结果，包含图像和 PDF 预览。</p>
      </div>
      <button class="ghost" type="button" @click="fetchHistory" :disabled="isLoadingHistory">
        {{ isLoadingHistory ? '刷新中...' : '刷新' }}
      </button>
    </div>
    <p v-if="historyError" class="error">{{ historyError }}</p>
    <ul v-if="historyItems.length" class="history-list">
      <li v-for="item in historyItems" :key="item.id" :class="{ active: selectedHistoryId === item.id }">
        <div>
          <strong>{{ item.fileName || '未命名文件' }}</strong>
          <small>{{ item.createdAt || '--' }}</small>
          <p class="muted">
            模式：{{ availableModes[item.mode]?.label || item.mode || '--' }} · 页数：{{ item.pages || 1 }} · {{ item.isPdf ? 'PDF' : '图像' }}
          </p>
        </div>
        <button type="button" class="ghost" @click="loadHistory(item.id)" :disabled="isRunning">
          {{ selectedHistoryId === item.id ? '查看中' : '查看' }}
        </button>
      </li>
    </ul>
    <p v-else class="muted">暂无缓存历史</p>
  </article>
</template>
