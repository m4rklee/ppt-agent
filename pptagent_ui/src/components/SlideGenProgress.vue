<template>
  <div class="slide-gen-progress" v-if="total > 0">
    <div class="progress-header">
      <span>逐页生成</span>
      <span class="count">{{ completed }} / {{ total }} 页</span>
    </div>
    <div class="progress-track">
      <div class="progress-fill" :style="{ width: percent + '%' }"></div>
    </div>
    <p v-if="currentPurpose && !allDone" class="current-slide">正在生成：{{ currentPurpose }}</p>
    <ul class="slide-list">
      <li
        v-for="slide in sortedSlides"
        :key="slide.index"
        :class="['slide-item', slideStatus(slide)]"
      >
        <span class="slide-idx">{{ slide.index }}</span>
        <span class="slide-purpose">{{ slide.purpose }}</span>
        <span class="slide-state">{{ slideStateLabel(slide) }}</span>
      </li>
    </ul>
  </div>
</template>

<script>
export default {
  name: 'SlideGenProgress',
  props: {
    slides: { type: Array, default: () => [] },
    completed: { type: Number, default: 0 },
    total: { type: Number, default: 0 },
    currentPurpose: { type: String, default: '' },
  },
  computed: {
    allDone() {
      return this.total > 0 && this.completed >= this.total
    },
    percent() {
      if (!this.total) return 0
      return Math.round((this.completed / this.total) * 100)
    },
    sortedSlides() {
      return [...this.slides].sort((a, b) => a.index - b.index)
    },
  },
  methods: {
    slideStatus(slide) {
      if (slide.success === true) return 'success'
      if (slide.success === false) return 'failed'
      return 'pending'
    },
    slideStateLabel(slide) {
      if (slide.success === true) return '完成'
      if (slide.success === false) return '失败'
      return '等待'
    },
  },
}
</script>

<style scoped>
.slide-gen-progress {
  margin-top: 12px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  font-size: 0.9em;
  margin-bottom: 6px;
}

.count {
  font-variant-numeric: tabular-nums;
  color: var(--color-primary);
  font-weight: 500;
}

.progress-track {
  height: 4px;
  background: var(--color-border);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.current-slide {
  font-size: 0.85em;
  color: var(--color-text-secondary);
  margin: 10px 0 8px;
}

.slide-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 200px;
  overflow-y: auto;
}

.slide-item {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 8px 4px;
  font-size: 0.85em;
  border-bottom: 1px solid var(--color-border);
}

.slide-item.success .slide-state { color: var(--color-success); }
.slide-item.failed .slide-state { color: var(--color-error); }
.slide-item.pending .slide-state { color: var(--color-text-secondary); }

.slide-idx {
  font-weight: 500;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.slide-purpose {
  color: var(--color-text);
}
</style>
