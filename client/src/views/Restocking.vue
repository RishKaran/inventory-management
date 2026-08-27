<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div class="card budget-card">
      <div class="card-header">
        <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
      </div>
      <div class="budget-controls">
        <input
          type="range"
          min="0"
          max="50000"
          step="500"
          v-model.number="budget"
          class="budget-slider"
        />
        <div class="budget-readout">{{ currencySymbol }}{{ budget.toLocaleString() }}</div>
      </div>

      <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else class="stats-grid budget-stats">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.estimatedCost') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ totalEstimatedCost.toLocaleString() }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ remainingBudget.toLocaleString() }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.itemsRecommended') }}</div>
          <div class="stat-value">{{ recommendations.length }}</div>
        </div>
      </div>
    </div>

    <div v-if="!loading && !error">
      <div v-if="recommendations.length === 0" class="card empty-state">
        <p>{{ t('restocking.noRecommendations') }}</p>
      </div>

      <div v-else class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendationsTitle') }} ({{ recommendations.length }})</h3>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.warehouse') }}</th>
                <th>{{ t('restocking.table.currentDemand') }}</th>
                <th>{{ t('restocking.table.forecastedDemand') }}</th>
                <th>{{ t('restocking.table.gap') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.recommendedQty') }}</th>
                <th>{{ t('restocking.table.estimatedCost') }}</th>
                <th>{{ t('restocking.table.funding') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommendations" :key="item.item_sku">
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ translateProductName(item.item_name) }}</td>
                <td>{{ item.warehouse }}</td>
                <td>{{ item.current_demand }}</td>
                <td>{{ item.forecasted_demand }}</td>
                <td>{{ item.demand_gap }}</td>
                <td>{{ currencySymbol }}{{ item.unit_cost.toLocaleString() }}</td>
                <td>{{ item.recommended_quantity }}</td>
                <td><strong>{{ currencySymbol }}{{ item.estimated_cost.toLocaleString() }}</strong></td>
                <td>
                  <span :class="['badge', item.fully_funded ? 'success' : 'warning']">
                    {{ item.fully_funded ? t('restocking.fullyFunded') : t('restocking.partial') }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="submit-row">
          <div v-if="submitSuccess" class="success-banner">{{ submitSuccess }}</div>
          <div v-if="submitError" class="error">{{ submitError }}</div>
          <button
            class="place-order-btn"
            :disabled="submitting || recommendations.length === 0"
            @click="submitOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName } = useI18n()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })

    const { selectedLocation } = useFilters()

    const budget = ref(10000)
    const recommendations = ref([])
    const totalEstimatedCost = ref(0)
    const remainingBudget = ref(0)

    const loading = ref(true)
    const error = ref(null)

    const submitting = ref(false)
    const submitError = ref(null)
    const submitSuccess = ref(null)

    const loadRecommendations = async () => {
      try {
        loading.value = true
        error.value = null
        const response = await api.getRestockRecommendations(budget.value, selectedLocation.value)
        recommendations.value = response.items
        totalEstimatedCost.value = response.total_estimated_cost
        remainingBudget.value = response.remaining_budget
      } catch (err) {
        error.value = 'Failed to load restock recommendations: ' + err.message
      } finally {
        loading.value = false
      }
    }

    let debounceTimer = null
    watch(budget, () => {
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        loadRecommendations()
      }, 300)
    })

    watch(selectedLocation, () => {
      loadRecommendations()
    })

    const submitOrder = async () => {
      if (submitting.value) return
      submitting.value = true
      submitError.value = null
      submitSuccess.value = null

      try {
        const items = recommendations.value.map(item => ({
          sku: item.item_sku,
          name: item.item_name,
          quantity: item.recommended_quantity,
          unit_price: item.unit_cost
        }))

        const payload = {
          budget: budget.value,
          warehouse: selectedLocation.value === 'all' ? null : selectedLocation.value,
          items
        }

        const response = await api.submitRestockOrder(payload)
        submitSuccess.value = t('restocking.submitSuccess', { orderNumber: response.order.order_number })
        await loadRecommendations()
      } catch (err) {
        submitError.value = err.response?.data?.detail || t('restocking.submitError')
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadRecommendations)

    return {
      t,
      budget,
      recommendations,
      totalEstimatedCost,
      remainingBudget,
      loading,
      error,
      submitting,
      submitError,
      submitSuccess,
      submitOrder,
      currencySymbol,
      translateProductName
    }
  }
}
</script>

<style scoped>
.budget-card {
  margin-bottom: 1.5rem;
}

.budget-controls {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  margin-bottom: 1.25rem;
}

.budget-slider {
  flex: 1;
  height: 6px;
  border-radius: 999px;
  background: #e2e8f0;
  outline: none;
  appearance: none;
  -webkit-appearance: none;
}

.budget-slider::-webkit-slider-thumb {
  appearance: none;
  -webkit-appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  cursor: pointer;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  cursor: pointer;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.budget-readout {
  min-width: 120px;
  text-align: right;
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-stats {
  margin-bottom: 0;
}

.empty-state {
  text-align: center;
  color: #64748b;
  padding: 2.5rem 1.25rem;
}

.submit-row {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.75rem;
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid #e2e8f0;
}

.success-banner {
  align-self: stretch;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.938rem;
}

.place-order-btn {
  background: #2563eb;
  color: #ffffff;
  border: none;
  padding: 0.625rem 1.5rem;
  border-radius: 8px;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}
</style>
