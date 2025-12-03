<script setup>
defineProps({
  activityLog: {
    type: Array,
    default: () => [],
  },
})
</script>

<template>
  <article class="card log-card">
    <h2>推理日志</h2>
    <ul v-if="activityLog.length">
      <li v-for="item in activityLog" :key="item.id">
        <strong>{{ item.timestamp }}</strong>
        <span>{{ item.message }}</span>
      </li>
    </ul>
    <p v-else class="muted">暂无日志</p>
  </article>
</template>
