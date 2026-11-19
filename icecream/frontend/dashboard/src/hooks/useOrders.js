import { useCallback, useEffect, useState } from 'react'
import { fetchOrders } from '../services/dashboardApi'

export function useOrders({ refreshKey = '' } = {}) {
  const [orders, setOrders] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const refreshOrders = useCallback(async () => {
    try {
      const data = await fetchOrders({ limit: 30, status: statusFilter })
      setOrders(Array.isArray(data) ? data : [])
      setError('')
    } catch (err) {
      setError(err.message || '주문 내역을 불러오지 못했습니다.')
    } finally {
      setIsLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    refreshOrders()
    const timer = setInterval(refreshOrders, 5000)
    return () => clearInterval(timer)
  }, [refreshOrders, refreshKey])

  return {
    orders,
    statusFilter,
    setStatusFilter,
    isLoading,
    error,
    refreshOrders,
  }
}
