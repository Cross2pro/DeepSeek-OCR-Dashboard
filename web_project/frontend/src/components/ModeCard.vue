<script setup>
defineProps({
  modeCards: {
    type: Array,
    default: () => [],
  },
  isFetchingModes: {
    type: Boolean,
    default: false,
  },
  onFetchModes: Function,
  onSelectMode: Function,
})
</script>

<template>
  <article class="card mode-card">
    <div class="card-header">
      <div>
        <h2>步骤 2 · 选择模式</h2>
        <p>根据速度与质量的平衡点选择推理配置。</p>
      </div>
      <button class="ghost" type="button" @click="onFetchModes" :disabled="isFetchingModes">
        {{ isFetchingModes ? '刷新中...' : '刷新' }}
      </button>
    </div>
    <div class="mode-grid">
      <button
        v-for="mode in modeCards"
        :key="mode.key"
        type="button"
        class="mode-tile"
        :class="{ active: mode.isActive }"
        @click="onSelectMode(mode.key)"
      >
        <div class="mode-title">
          <h3>{{ mode.label }}</h3>
          <small>{{ mode.key }}</small>
        </div>
        <p>{{ mode.description }}</p>
        <ul>
          <li>质量：{{ mode.quality }}</li>
          <li>速度：{{ mode.speed }}</li>
          <li>尺寸：{{ mode.base_size }} / {{ mode.image_size }}</li>
        </ul>
      </button>
    </div>
  </article>
</template>
