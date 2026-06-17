<template>
  <div class="pipeline-timeline">
    <div class="timeline-header">
      <h3>生成流程</h3>
      <span class="elapsed">总耗时 {{ formatMs(elapsedMs) }}</span>
    </div>
    <ul class="timeline-list">
      <li
        v-for="stage in stages"
        :key="stage.id"
        :class="['timeline-item', stage.status, { selected: selectedId === stage.id }]"
        @click="$emit('select', stage.id)"
      >
        <div class="timeline-content">
          <div class="stage-title">{{ stage.label }}</div>
          <div class="stage-meta">
            <span :class="['status-badge', stage.status]">{{ statusLabel(stage.status) }}</span>
            <span v-if="stage.elapsed_ms != null" class="stage-time">{{ formatMs(stage.elapsed_ms) }}</span>
            <span v-if="stage.cached" class="cached-badge">缓存</span>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<script>
export default {
  name: 'PipelineTimeline',
  props: {
    stages: { type: Array, required: true },
    elapsedMs: { type: Number, default: 0 },
    selectedId: { type: String, default: null },
  },
  emits: ['select'],
  methods: {
    formatMs(ms) {
      if (!ms && ms !== 0) return '--'
      const sec = Math.floor(ms / 1000)
      const min = Math.floor(sec / 60)
      const s = sec % 60
      if (min > 0) return `${min} 分 ${s} 秒`
      return `${sec} 秒`
    },
    statusLabel(status) {
      const map = {
        pending: '等待',
        running: '进行中',
        waiting: '待确认',
        completed: '完成',
        failed: '失败',
      }
      return map[status] || status
    },
  },
}
</script>

<style scoped>
.pipeline-timeline {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 16px;
  height: 100%;
  overflow-y: auto;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border);
}

.timeline-header h3 {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--color-text);
}

.elapsed {
  font-size: 0.8rem;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.timeline-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.timeline-item {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  border-left: 2px solid transparent;
  transition: background 0.12s, border-color 0.12s;
}

.timeline-item:hover {
  background: var(--color-bg);
}

.timeline-item.selected {
  background: var(--color-primary-light);
  border-left-color: var(--color-primary);
}

.timeline-item.running {
  animation: subtle-pulse 2s ease-in-out infinite;
}

@keyframes subtle-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.85; }
}

.stage-title {
  font-weight: 500;
  font-size: 0.9rem;
  color: var(--color-text);
  line-height: 1.3;
}

.stage-meta {
  margin-top: 4px;
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 0.75rem;
}

.status-badge {
  color: var(--color-text-secondary);
}

.status-badge.running {
  color: var(--color-primary);
  font-weight: 500;
}

.status-badge.waiting {
  color: var(--color-warning);
  font-weight: 500;
}

.status-badge.completed {
  color: var(--color-success);
}

.status-badge.failed {
  color: var(--color-error);
}

.stage-time {
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.cached-badge {
  color: var(--color-warning);
  font-size: 0.85em;
}
</style>
