<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

const { t, currentCurrency } = useI18n()

const forecasts = ref([])
const loading = ref(true)
const error = ref(null)
const budget = ref(10000)
const submitting = ref(false)
const successMessage = ref(null)
const submitError = ref(null)

// Costs are in USD; convert for the active currency
const formatCost = (amount) => formatCurrency(amount, currentCurrency.value)

// Greedy fill: only items with growing demand are candidates, ordered by the
// size of the increase (largest first). Quantity is the increase itself. An item
// that does not fit in the remaining budget is skipped, and we keep trying the
// following (smaller-increase) items.
const recommendations = computed(() => {
  const candidates = forecasts.value
    .map(f => ({ ...f, increase: f.forecasted_demand - f.current_demand }))
    .filter(f => f.increase > 0)
    .sort((a, b) => b.increase - a.increase)

  let remaining = budget.value
  const picked = []
  for (const f of candidates) {
    const lineTotal = f.increase * f.unit_cost
    if (lineTotal <= remaining) {
      picked.push({ ...f, quantity: f.increase, line_total: lineTotal })
      remaining -= lineTotal
    }
  }
  return picked
})

const totalCost = computed(() => recommendations.value.reduce((s, r) => s + r.line_total, 0))
const remainingBudget = computed(() => budget.value - totalCost.value)
const longestLeadTime = computed(() =>
  recommendations.value.reduce((m, r) => Math.max(m, r.lead_time_days), 0)
)

const trendClass = (trend) => ({ increasing: 'danger', decreasing: 'success', stable: 'info' }[trend] || 'info')

const loadForecasts = async () => {
  loading.value = true
  error.value = null
  try {
    forecasts.value = await api.getDemandForecasts()
  } catch (err) {
    error.value = t('restocking.loadError') + ': ' + err.message
  } finally {
    loading.value = false
  }
}

const placeOrder = async () => {
  if (submitting.value || recommendations.value.length === 0) return
  submitting.value = true
  successMessage.value = null
  submitError.value = null
  try {
    const order = await api.createRestockingOrder({
      budget: budget.value,
      items: recommendations.value.map(r => ({
        item_sku: r.item_sku,
        item_name: r.item_name,
        quantity: r.quantity,
        unit_cost: r.unit_cost
      }))
    })
    successMessage.value = t('restocking.success', {
      orderNumber: order.order_number,
      days: order.lead_time_days
    })
  } catch (err) {
    submitError.value = err.response?.data?.detail || t('restocking.failed')
  } finally {
    submitting.value = false
  }
}

onMounted(loadForecasts)
</script>

<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.subtitle') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <label class="budget-label" for="budget-slider">
          {{ t('restocking.budgetLabel') }}: <strong>{{ formatCost(budget) }}</strong>
        </label>
        <input
          id="budget-slider"
          v-model.number="budget"
          class="budget-slider"
          type="range"
          min="0"
          max="50000"
          step="500"
        />
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }}</h3>
        </div>

        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.empty') }}
        </div>
        <template v-else>
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th>{{ t('restocking.columns.sku') }}</th>
                  <th>{{ t('restocking.columns.name') }}</th>
                  <th>{{ t('restocking.columns.trend') }}</th>
                  <th>{{ t('restocking.columns.quantity') }}</th>
                  <th>{{ t('restocking.columns.unitCost') }}</th>
                  <th>{{ t('restocking.columns.lineTotal') }}</th>
                  <th>{{ t('restocking.columns.leadTime') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in recommendations" :key="r.item_sku">
                  <td><strong>{{ r.item_sku }}</strong></td>
                  <td>{{ r.item_name }}</td>
                  <td>
                    <span :class="['badge', trendClass(r.trend)]">{{ t(`trends.${r.trend}`) }}</span>
                  </td>
                  <td>{{ r.quantity.toLocaleString() }}</td>
                  <td>{{ formatCost(r.unit_cost) }}</td>
                  <td><strong>{{ formatCost(r.line_total) }}</strong></td>
                  <td>{{ r.lead_time_days }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="summary">
            <div class="summary-item">
              <span class="summary-label">{{ t('restocking.summary.totalCost') }}</span>
              <span class="summary-value">{{ formatCost(totalCost) }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">{{ t('restocking.summary.remainingBudget') }}</span>
              <span class="summary-value">{{ formatCost(remainingBudget) }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">{{ t('restocking.summary.longestLeadTime') }}</span>
              <span class="summary-value">{{ t('restocking.days', { count: longestLeadTime }) }}</span>
            </div>
          </div>
        </template>

        <div class="actions">
          <button
            type="button"
            class="place-order"
            :disabled="recommendations.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
          </button>
        </div>
        <div v-if="successMessage" class="message success-message">{{ successMessage }}</div>
        <div v-if="submitError" class="message error-message">{{ submitError }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.budget-card {
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-label {
  display: block;
  margin-bottom: 0.75rem;
  color: #64748b;
  font-size: 0.875rem;
}

.budget-label strong {
  color: #0f172a;
  font-size: 1.125rem;
}

.budget-slider {
  width: 100%;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

.summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid #e2e8f0;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.summary-label {
  font-size: 0.813rem;
  color: #64748b;
}

.summary-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: #0f172a;
}

.actions {
  padding: 1rem 1.5rem;
  border-top: 1px solid #e2e8f0;
}

.place-order {
  padding: 0.625rem 1.25rem;
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
}

.place-order:hover:not(:disabled) {
  background: #1e293b;
}

.place-order:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}

.message {
  margin: 0 1.5rem 1.25rem;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.success-message {
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.error-message {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}
</style>
