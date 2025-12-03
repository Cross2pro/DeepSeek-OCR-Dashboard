<script setup>
defineProps({
  hasLayout: {
    type: Boolean,
    default: false,
  },
  layoutRegions: {
    type: Array,
    default: () => [],
  },
  activeRegionKey: {
    type: String,
    default: '',
  },
  handleRegionSelect: Function,
  selectedRegion: {
    type: Object,
    default: null,
  },
  selectedRegionSnippet: {
    type: String,
    default: '',
  },
  copySelectedRegion: Function,
  regionOutputView: {
    type: String,
    default: 'raw',
  },
  regionHasHtmlTable: {
    type: Boolean,
    default: false,
  },
  regionHtmlTableOutput: {
    type: String,
    default: '',
  },
  regionMarkdownTableOutput: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:regionOutputView'])

function setRegionOutputView(view) {
  emit('update:regionOutputView', view)
}
</script>

<template>
  <article class="card layout-details-card" v-if="hasLayout">
    <div class="card-header">
      <div>
        <h2>标注详情</h2>
        <p>选择任意方框以查看位置信息与文本。</p>
      </div>
      <button class="ghost" type="button" :disabled="!selectedRegionSnippet" @click="copySelectedRegion">
        复制区域文本
      </button>
    </div>
    <div class="layout-chips">
      <button
        v-for="region in layoutRegions"
        :key="region.key"
        type="button"
        :class="{ active: region.key === activeRegionKey }"
        @click="handleRegionSelect(region.key)"
      >
        <span>{{ region.label }}</span>
        <small>#{{ region.box.index }}</small>
      </button>
    </div>
    <div v-if="selectedRegion" class="layout-inspector">
      <p><strong>类型：</strong>{{ selectedRegion.label }}</p>
      <p><strong>坐标：</strong>{{ selectedRegion.box.absolute.join(', ') }}</p>
      <div class="output-switch">
        <span>内容</span>
        <div class="output-tabs">
          <button
            type="button"
            :class="{ active: regionOutputView === 'raw' }"
            @click="setRegionOutputView('raw')"
          >
            原文
          </button>
          <button
            type="button"
            :class="{ active: regionOutputView === 'html' }"
            :disabled="!regionHasHtmlTable"
            @click="setRegionOutputView('html')"
          >
            HTML 表格
          </button>
          <button
            type="button"
            :class="{ active: regionOutputView === 'markdown' }"
            :disabled="!regionHasHtmlTable"
            @click="setRegionOutputView('markdown')"
          >
            Markdown 表格
          </button>
        </div>
      </div>
      <p v-if="selectedRegionSnippet && !regionHasHtmlTable" class="muted helper">
        未检测到表格标签，显示原文。
      </p>
      <div v-if="regionOutputView === 'html' && regionHtmlTableOutput" class="html-preview" v-html="regionHtmlTableOutput"></div>
      <pre v-else-if="regionOutputView === 'markdown' && regionMarkdownTableOutput">{{ regionMarkdownTableOutput }}</pre>
      <pre v-else>{{ selectedRegionSnippet || '该区域暂未匹配到文本，可参考全量输出。' }}</pre>
    </div>
    <p v-else class="muted">选择任意区域以查看具体内容。</p>
  </article>

  <article class="card layout-details-card muted-card" v-else>
    <p class="muted">完成一次推理后，可在此查看标注详情。</p>
  </article>
</template>
