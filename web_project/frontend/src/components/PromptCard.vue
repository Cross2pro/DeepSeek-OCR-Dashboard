<script setup>
defineProps({
  modelValue: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:modelValue'])

function handleInput(event) {
  emit('update:modelValue', event.target.value)
}
</script>

<template>
  <article class="card prompt-card">
    <h2>配置提示词</h2>
    <textarea
      rows="4"
      :value="modelValue"
      @input="handleInput"
      placeholder="请输入包含 <image> 的提示词"
    ></textarea>
    <small>提示词会拼接在模型输入中，默认会自动添加 &lt;image&gt;。</small>
  </article>
</template>
