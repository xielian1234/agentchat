import { fetchEventSource } from '@microsoft/fetch-event-source'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// 灵寻步骤完整定义（用于「复制为新任务」与「单节点重试」）
export interface LingSeekStep {
  thought: string
  step_id: string
  title: string
  target: string
  workflow: any
  precautions: string
  input_thought: string
  input: string[]
  result?: string
}

// 单步骤执行结果（step_result 事件负载）
export interface LingSeekStepResult {
  step_id: string
  title: string
  message: string
  status?: 'completed' | 'failed' | 'executing' | 'pending'
  error?: string
  thought?: string
  target?: string
  workflow?: any
  precautions?: string
  input_thought?: string
}

// 生成灵寻的指导提示（流式）
export const generateLingSeekGuidePromptAPI = async (
  data: {
    query: string
    model_id?: string
    plugins?: string[]
    web_search?: boolean
    mcp_servers?: string[]
    file_urls?: string[]
  },
  onMessage: (data: any) => void,
  onError?: (error: any) => void,
  onClose?: () => void
) => {
  const token = localStorage.getItem('token')
  
  console.log('=== generateLingSeekGuidePromptAPI 调用 ===')
  console.log('参数:', data)
  console.log('Token:', token ? `${token.substring(0, 20)}...` : '无')
  console.log('请求 URL:', `${BASE_URL}/api/v1/workspace/lingseek/guide_prompt`)
  
  const ctrl = new AbortController()
  
  try {
    await fetchEventSource(`${BASE_URL}/api/v1/workspace/lingseek/guide_prompt`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(data),
      signal: ctrl.signal,
      openWhenHidden: true,
      onmessage(event) {
        console.log('📨 收到原始消息:', event.data)
        if (event.data) {
          try {
            // 后端返回的是 JSON 格式: { "event": "...", "data": { "chunk": "..." } }
            const parsedData = JSON.parse(event.data)
            console.log('📦 解析后的数据:', parsedData)
            
            if (parsedData.data && parsedData.data.chunk) {
              const chunk = parsedData.data.chunk
              console.log('📝 提取的 chunk:', chunk)
              onMessage(chunk)
            }
          } catch (error) {
            console.error('❌ JSON 解析失败:', error, '原始数据:', event.data)
            // 如果解析失败，尝试直接使用原始数据
            onMessage(event.data)
          }
        }
      },
      onerror(err) {
        console.error('Stream 错误:', err)
        onError?.(err)
        // 不要 throw，而是中断连接
        ctrl.abort()
      },
      onclose() {
        console.log('Stream 关闭')
        onClose?.()
      }
    })
  } catch (error) {
    console.error('fetchEventSource 异常:', error)
    if (error.name !== 'AbortError') {
      onError?.(error)
    }
  }
}

// 根据用户反馈重新生成指导提示（流式）
export const regenerateLingSeekGuidePromptAPI = async (
  data: {
    query: string
    guide_prompt: string
    feedback: string
    model_id?: string
    web_search?: boolean
    plugins?: string[]
    mcp_servers?: string[]
    file_urls?: string[]
  },
  onMessage: (data: any) => void,
  onError?: (error: any) => void,
  onClose?: () => void
) => {
  const token = localStorage.getItem('token')
  
  console.log('开始调用 guide_prompt/feedback 接口，参数:', data)
  
  const ctrl = new AbortController()
  
  try {
    await fetchEventSource(`${BASE_URL}/api/v1/workspace/lingseek/guide_prompt/feedback`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(data),
      signal: ctrl.signal,
      openWhenHidden: true,
      onmessage(event) {
        console.log('📨 收到原始消息:', event.data)
        if (event.data) {
          try {
            // 后端返回的是 JSON 格式: { "event": "...", "data": { "chunk": "..." } }
            const parsedData = JSON.parse(event.data)
            console.log('📦 解析后的数据:', parsedData)
            
            if (parsedData.data && parsedData.data.chunk) {
              const chunk = parsedData.data.chunk
              console.log('📝 提取的 chunk:', chunk)
              onMessage(chunk)
            }
          } catch (error) {
            console.error('❌ JSON 解析失败:', error, '原始数据:', event.data)
            // 如果解析失败，尝试直接使用原始数据
            onMessage(event.data)
          }
        }
      },
      onerror(err) {
        console.error('Stream 错误:', err)
        onError?.(err)
        ctrl.abort()
      },
      onclose() {
        console.log('Stream 关闭')
        onClose?.()
      }
    })
  } catch (error) {
    console.error('fetchEventSource 异常:', error)
    if (error.name !== 'AbortError') {
      onError?.(error)
    }
  }
}

// 生成灵寻任务列表（流式）
export const generateLingSeekTasksAPI = async (
  data: {
    guide_prompt: string
    model_id?: string
  },
  onMessage: (data: any) => void,
  onError?: (error: any) => void,
  onClose?: () => void
) => {
  const token = localStorage.getItem('token')
  
  console.log('开始调用 task 接口，参数:', data)
  
  const ctrl = new AbortController()
  
  try {
    await fetchEventSource(`${BASE_URL}/api/v1/workspace/lingseek/task`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(data),
      signal: ctrl.signal,
      openWhenHidden: true,
      onmessage(event) {
        console.log('📨 收到原始消息:', event.data)
        if (event.data) {
          try {
            // 后端返回的是 JSON 格式: { "event": "...", "data": { "chunk": "..." } }
            const parsedData = JSON.parse(event.data)
            console.log('📦 解析后的数据:', parsedData)
            
            if (parsedData.data && parsedData.data.chunk) {
              const chunk = parsedData.data.chunk
              console.log('📝 提取的 chunk:', chunk)
              onMessage(chunk)
            }
          } catch (error) {
            console.error('❌ JSON 解析失败:', error, '原始数据:', event.data)
            // 如果解析失败，尝试直接使用原始数据
            onMessage(event.data)
          }
        }
      },
      onerror(err) {
        console.error('Stream 错误:', err)
        onError?.(err)
        ctrl.abort()
      },
      onclose() {
        console.log('Stream 关闭')
        onClose?.()
      }
    })
  } catch (error) {
    console.error('fetchEventSource 异常:', error)
    if (error.name !== 'AbortError') {
      onError?.(error)
    }
  }
}

// 开始执行灵寻任务（流式）
export const startLingSeekTaskAPI = async (
  data: {
    query: string
    guide_prompt: string
    model_id?: string
    web_search?: boolean
    plugins?: string[]
    mcp_servers?: string[]
    file_urls?: string[]
  },
  onMessage: (data: any) => void,
  onTaskGraph?: (payload: { graph: any[]; steps: LingSeekStep[] }) => void,  // 处理任务图数据（含完整步骤定义）
  onStepResult?: (stepData: LingSeekStepResult) => void,  // 处理步骤结果（含完整元数据）
  onTaskResult?: (message: string) => void,  // 处理任务最终结果
  onStepStart?: (stepData: { step_id: string; title: string }) => void,  // 处理节点开始执行
  onError?: (error: any) => void,
  onClose?: () => void,
  signal?: AbortSignal  // 外部传入用于停止执行
) => {
  const token = localStorage.getItem('token')

  console.log('开始调用 task_start 接口，参数:', data)

  const ctrl = new AbortController()
  const effectiveSignal = signal ?? ctrl.signal

  try {
    await fetchEventSource(`${BASE_URL}/api/v1/workspace/lingseek/task_start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(data),
      signal: effectiveSignal,
      openWhenHidden: true,
      onmessage(event) {
        console.log('📨 收到原始消息:', event.data)
        if (event.data) {
          try {
            // 后端返回的是 JSON 格式: { "event": "...", "data": {...} }
            const parsedData = JSON.parse(event.data)
            console.log('📦 解析后的数据:', parsedData)

            // 处理不同类型的事件
            if (parsedData.event === 'generate_tasks') {
              // 处理任务图数据（含完整步骤定义，供重试/复制使用）
              console.log('📊 收到任务图数据:', parsedData.data)
              onTaskGraph?.({ graph: parsedData.data?.graph ?? [], steps: parsedData.data?.steps ?? [] })
            } else if (parsedData.event === 'step_start') {
              console.log('▶️ 节点开始执行:', parsedData.data)
              onStepStart?.(parsedData.data)
            } else if (parsedData.event === 'step_result') {
              // 处理步骤执行结果（含完整元数据）
              console.log('✅ 收到步骤结果:', parsedData.data)
              onStepResult?.(parsedData.data)
            } else if (parsedData.event === 'task_result') {
              // 处理任务最终结果（流式）
              console.log('📄 收到任务结果数据块:', parsedData.data?.message)
              onTaskResult?.(parsedData.data?.message ?? '')
            } else if (parsedData.data?.chunk) {
              // 处理文本块数据
              const chunk = parsedData.data.chunk
              console.log('📝 提取的 chunk:', chunk)
              onMessage(chunk)
            } else {
              // 其他类型的数据，直接传递
              onMessage(parsedData)
            }
          } catch (error) {
            console.error('❌ JSON 解析失败:', error, '原始数据:', event.data)
            // 如果解析失败，尝试直接使用原始数据
            onMessage(event.data)
          }
        }
      },
      onerror(err) {
        console.error('Stream 错误:', err)
        onError?.(err)
        ctrl.abort()
      },
      onclose() {
        console.log('Stream 关闭')
        onClose?.()
      }
    })
  } catch (error) {
    console.error('fetchEventSource 异常:', error)
    if (error.name !== 'AbortError') {
      onError?.(error)
    }
  }
}

// 单节点重试（流式）
export const retryLingSeekStepAPI = async (
  data: {
    query: string
    guide_prompt: string
    model_id?: string
    web_search?: boolean
    plugins?: string[]
    mcp_servers?: string[]
    file_urls?: string[]
    steps: LingSeekStep[]
    retry_step_id: string
  },
  onMessage: (data: any) => void,
  onStepStart?: (stepData: { step_id: string; title: string }) => void,
  onStepResult?: (stepData: LingSeekStepResult) => void,
  onTaskResult?: (message: string) => void,
  onError?: (error: any) => void,
  onClose?: () => void,
  signal?: AbortSignal
) => {
  const token = localStorage.getItem('token')

  console.log('开始调用 task_step_retry 接口，参数:', data)

  const ctrl = new AbortController()
  const effectiveSignal = signal ?? ctrl.signal

  try {
    await fetchEventSource(`${BASE_URL}/api/v1/workspace/lingseek/task_step_retry`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(data),
      signal: effectiveSignal,
      openWhenHidden: true,
      onmessage(event) {
        console.log('📨 收到原始消息:', event.data)
        if (event.data) {
          try {
            const parsedData = JSON.parse(event.data)
            console.log('📦 解析后的数据:', parsedData)

            if (parsedData.event === 'step_start') {
              onStepStart?.(parsedData.data)
            } else if (parsedData.event === 'step_result') {
              onStepResult?.(parsedData.data)
            } else if (parsedData.event === 'task_result') {
              onTaskResult?.(parsedData.data?.message ?? '')
            } else {
              onMessage(parsedData)
            }
          } catch (error) {
            console.error('❌ JSON 解析失败:', error, '原始数据:', event.data)
            onMessage(event.data)
          }
        }
      },
      onerror(err) {
        console.error('Stream 错误:', err)
        onError?.(err)
        ctrl.abort()
      },
      onclose() {
        console.log('Stream 关闭')
        onClose?.()
      }
    })
  } catch (error) {
    console.error('fetchEventSource 异常:', error)
    if (error.name !== 'AbortError') {
      onError?.(error)
    }
  }
}

