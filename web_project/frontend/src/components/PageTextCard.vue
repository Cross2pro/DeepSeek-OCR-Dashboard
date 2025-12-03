<script setup>
defineProps({
  currentPage: {
    type: Object,
    default: null,
  },
  currentPageCleanText: {
    type: String,
    default: '',
  },
  copyCurrentPageText: Function,
  activePageIndex: {
    type: Number,
    default: 0,
  },
})
</script>

<template>
  <article class="card page-text-card" v-if="currentPage">
    <div class="card-header">
      <div>
        <h2>当前页文本</h2>
        <p>第 {{ currentPage.pageIndex + 1 }} 页识别结果</p>
      </div>
      <button class="ghost" type="button" :disabled="!currentPageCleanText" @click="copyCurrentPageText">
        复制当前页
      </button>
    </div>
    <pre>{{ currentPageCleanText || '暂无文本' }}</pre>
  </article>
</template>
