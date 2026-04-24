const API = 'http://localhost:8000/api'
let token = localStorage.getItem('token') || ''
let currentExamId = null

const loginCard = document.getElementById('loginCard')
const dashboard = document.getElementById('dashboard')
const resultCard = document.getElementById('resultCard')
const loginStatus = document.getElementById('loginStatus')
const examSelect = document.getElementById('examSelect')
const questionsList = document.getElementById('questionsList')

const resultTitle = document.getElementById('resultTitle')
const resultSubtitle = document.getElementById('resultSubtitle')
const resultTotal = document.getElementById('resultTotal')
const resultTotalMax = document.getElementById('resultTotalMax')
const resultMeta = document.getElementById('resultMeta')
const resultTableBody = document.querySelector('#resultTable tbody')

const logoutBtn = document.getElementById('logoutBtn')

const globalStatus = document.getElementById('globalStatus')
const statusText = document.getElementById('statusText')
const statusSpinner = document.getElementById('statusSpinner')

const loginBtn = document.getElementById('loginBtn')
const createExamBtn = document.getElementById('createExamBtn')
const loadExamBtn = document.getElementById('loadExamBtn')
const uploadQuestionPaperBtn = document.getElementById('uploadQuestionPaperBtn')
const uploadMarkingSchemeBtn = document.getElementById('uploadMarkingSchemeBtn')
const uploadSheetBtn = document.getElementById('uploadSheetBtn')
const exportExcelBtn = document.getElementById('exportExcelBtn')

function setAuthUI() {
  const loggedIn = !!token
  if (loggedIn) {
    document.body.classList.add('authenticated')
    loginCard.classList.add('hidden')
    dashboard.classList.remove('hidden')
    logoutBtn.classList.remove('hidden')
    loginStatus.textContent = ''
  } else {
    document.body.classList.remove('authenticated')
    loginCard.classList.remove('hidden')
    dashboard.classList.add('hidden')
    logoutBtn.classList.add('hidden')
  }
}

function setStatus(message, type = 'info', busy = false) {
  globalStatus.classList.remove('hidden', 'info', 'success', 'error')
  globalStatus.classList.add(type)
  statusText.textContent = message
  statusSpinner.classList.toggle('hidden', !busy)
}

function getErrorMessage(err) {
  const raw = err && err.message ? String(err.message) : 'Unknown error'
  return raw.length > 260 ? `${raw.slice(0, 260)}...` : raw
}

function setButtonsDisabled(disabled) {
  const buttons = [
    loginBtn,
    createExamBtn,
    loadExamBtn,
    uploadQuestionPaperBtn,
    uploadMarkingSchemeBtn,
    uploadSheetBtn,
    exportExcelBtn,
    ...document.querySelectorAll('button.eval-btn'),
    ...document.querySelectorAll('button.delete-btn'),
  ]
  buttons.forEach((b) => {
    if (b) b.disabled = disabled
  })
}

async function runTask(startMessage, fn, options = {}) {
  const { successMessage = 'Done', showSuccess = true, blockUI = true } = options
  try {
    setStatus(startMessage, 'info', true)
    if (blockUI) setButtonsDisabled(true)
    const res = await fn()
    if (showSuccess) setStatus(successMessage, 'success', false)
    return res
  } catch (err) {
    setStatus(`Error: ${getErrorMessage(err)}`, 'error', false)
    throw err
  } finally {
    if (blockUI) setButtonsDisabled(false)
  }
}

async function request(path, opts = {}) {
  const headers = opts.headers || {}
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${API}${path}`, { ...opts, headers })
  const ct = res.headers.get('content-type') || ''
  const data = ct.includes('application/json') ? await res.json() : await res.text()
  if (!res.ok) throw new Error(data.detail || JSON.stringify(data))
  return data
}

function statusBadge(status) {
  const value = (status || '').toLowerCase()
  if (value === 'completed') return '<span class="badge success">Completed</span>'
  if (value === 'failed') return '<span class="badge error">Failed</span>'
  return '<span class="badge warn">Needs Review</span>'
}

function truncate(text, max = 160) {
  const clean = (text || '').trim()
  if (clean.length <= max) return clean
  return `${clean.slice(0, max)}...`
}

function renderQuestions(questions = []) {
  if (!questions.length) {
    questionsList.className = 'questions-list empty'
    questionsList.textContent = 'No questions parsed yet.'
    return
  }

  questionsList.className = 'questions-list'
  questionsList.innerHTML = questions
    .map((q) => {
      const keywords = (q.keywords || []).length ? q.keywords.join(', ') : 'No keywords'
      return `
        <article class="question-item">
          <div class="question-head">
            <span>Q${q.question_number}</span>
            <span>${q.max_marks} marks</span>
          </div>
          <div class="question-prompt">${q.prompt}</div>
          <div class="small">Keywords: ${keywords}</div>
        </article>
      `
    })
    .join('')
}

async function loadExams() {
  const exams = await request('/exams')
  examSelect.innerHTML = ''
  exams.forEach((e) => {
    const opt = document.createElement('option')
    opt.value = e.id
    opt.textContent = `${e.id} - ${e.title}`
    examSelect.appendChild(opt)
  })
  if (exams.length) currentExamId = Number(exams[0].id)
}

async function loadExamDetail() {
  if (!currentExamId) return
  const exam = await request(`/exams/${currentExamId}`)
  renderQuestions(exam.questions || [])
  await loadSheets()
}

async function loadSheets() {
  if (!currentExamId) return
  const rows = await request(`/exams/${currentExamId}/answersheets`)
  const tbody = document.querySelector('#sheetsTable tbody')
  tbody.innerHTML = ''

  rows.forEach((row) => {
    const tr = document.createElement('tr')
    const scoreText = row.evaluated
      ? `${Number(row.total_score || 0).toFixed(2)} / ${Number(row.max_total || 0).toFixed(2)}`
      : '-'
    tr.innerHTML = `
      <td>${row.id}</td>
      <td>${row.student_name}</td>
      <td>${statusBadge(row.ocr_status)}</td>
      <td>${row.ocr_confidence ? row.ocr_confidence.toFixed(2) : 'N/A'}</td>
      <td>${scoreText}</td>
      <td>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <button class="btn eval-btn" data-id="${row.id}">Evaluate</button>
          <button class="btn danger delete-btn" data-id="${row.id}">Delete</button>
        </div>
      </td>
    `

    const evalBtn = tr.querySelector('.eval-btn')
    const deleteBtn = tr.querySelector('.delete-btn')

    evalBtn.addEventListener('click', async () => {
      try {
        await runTask(`Evaluating sheet #${row.id} with Hugging Face LLM...`, async () => {
          evalBtn.disabled = true
          const result = await request(`/answersheets/${row.id}/evaluate`, { method: 'POST' })
          renderEvaluationResult(result)
          await loadSheets()
        }, { successMessage: `Evaluation finished for ${row.student_name}` })
      } catch (err) {
        console.error(err)
      } finally {
        evalBtn.disabled = false
      }
    })

    deleteBtn.addEventListener('click', async () => {
      const ok = window.confirm(`Delete answer sheet #${row.id} for ${row.student_name}?`)
      if (!ok) return
      try {
        await runTask(`Deleting sheet #${row.id}...`, async () => {
          await request(`/answersheets/${row.id}`, { method: 'DELETE' })
          await loadSheets()
        }, { successMessage: `Deleted sheet #${row.id}.` })
      } catch (err) {
        console.error(err)
      }
    })

    tbody.appendChild(tr)
  })
}

function renderEvaluationResult(data) {
  resultCard.classList.remove('hidden')

  const results = data.results || []
  const totalScored = Number(data.total_marks || 0)
  const totalMax = results.reduce((sum, r) => sum + Number(r.max_marks || 0), 0)
  const percent = totalMax > 0 ? (totalScored / totalMax) * 100 : 0

  resultTitle.textContent = `Evaluation Report - ${data.student_name || 'Student'}`
  resultSubtitle.textContent = `Answer Sheet ID: ${data.sheet_id}`
  resultTotal.textContent = totalScored.toFixed(2)
  resultTotalMax.textContent = `/ ${totalMax.toFixed(2)}`

  resultMeta.innerHTML = `
    <div class="meta-item"><div class="label">Total Questions</div><div class="value">${results.length}</div></div>
    <div class="meta-item"><div class="label">Percentage</div><div class="value">${percent.toFixed(1)}%</div></div>
    <div class="meta-item"><div class="label">Final Grade Hint</div><div class="value">${percent >= 80 ? 'Excellent' : percent >= 60 ? 'Good' : percent >= 40 ? 'Needs Work' : 'At Risk'}</div></div>
  `

  resultTableBody.innerHTML = results
    .map((r) => {
      const scoreBreakdown = `
        <div>Sem: ${Number(r.semantic_similarity || 0).toFixed(2)}</div>
        <div>Key: ${Number(r.keyword_coverage || 0).toFixed(2)}</div>
        <div>Comp: ${Number(r.completeness || 0).toFixed(2)}</div>
      `

      return `
        <tr>
          <td>Q${r.question_number}</td>
          <td>${truncate(r.question, 140)}</td>
          <td>${truncate(r.student_answer, 220)}</td>
          <td>${truncate(r.rubric, 220)}</td>
          <td>${scoreBreakdown}</td>
          <td><strong>${Number(r.awarded_marks || 0).toFixed(2)} / ${Number(r.max_marks || 0).toFixed(2)}</strong></td>
          <td>${truncate(r.feedback || '-', 160)}</td>
        </tr>
      `
    })
    .join('')

  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
}

document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault()
  try {
    await runTask('Logging in...', async () => {
      const username = document.getElementById('username').value
      const password = document.getElementById('password').value
      const data = await request('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      token = data.access_token
      localStorage.setItem('token', token)
      loginStatus.textContent = 'Login successful'
      setAuthUI()
      await loadExams()
      await loadExamDetail()
    }, { successMessage: 'Logged in successfully.' })
  } catch (err) {
    loginStatus.textContent = `Login failed: ${getErrorMessage(err)}`
  }
})

createExamBtn.addEventListener('click', async () => {
  const title = document.getElementById('examTitle').value.trim()
  if (!title) {
    setStatus('Please enter an assessment title.', 'error', false)
    return
  }

  try {
    await runTask('Creating assessment...', async () => {
      await request('/exams', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      })
      document.getElementById('examTitle').value = ''
      await loadExams()
      await loadExamDetail()
    }, { successMessage: 'Assessment created.' })
  } catch (err) {
    console.error(err)
  }
})

loadExamBtn.addEventListener('click', async () => {
  if (!examSelect.value) {
    setStatus('No assessment available. Create one first.', 'error', false)
    return
  }

  currentExamId = Number(examSelect.value)
  try {
    await runTask(`Loading assessment #${currentExamId}...`, async () => {
      await loadExamDetail()
    }, { successMessage: 'Assessment loaded.' })
  } catch (err) {
    console.error(err)
  }
})

uploadQuestionPaperBtn.addEventListener('click', async () => {
  if (!currentExamId) {
    setStatus('Create/load an assessment first.', 'error', false)
    return
  }

  const file = document.getElementById('questionPaperInput').files[0]
  if (!file) {
    setStatus('Choose a question paper file.', 'error', false)
    return
  }

  try {
    await runTask('Uploading question paper...', async () => {
      const form = new FormData()
      form.append('file', file)
      await request(`/exams/${currentExamId}/question-paper`, { method: 'POST', body: form })
      await loadExamDetail()
    }, { successMessage: 'Question paper uploaded.' })
  } catch (err) {
    console.error(err)
  }
})

uploadMarkingSchemeBtn.addEventListener('click', async () => {
  if (!currentExamId) {
    setStatus('Create/load an assessment first.', 'error', false)
    return
  }

  const file = document.getElementById('markingSchemeInput').files[0]
  if (!file) {
    setStatus('Choose a marking scheme file.', 'error', false)
    return
  }

  try {
    await runTask('Uploading and parsing marking scheme...', async () => {
      const form = new FormData()
      form.append('file', file)
      const res = await request(`/exams/${currentExamId}/marking-scheme`, { method: 'POST', body: form })
      await loadExamDetail()
      setStatus(`Marking scheme parsed: ${res.parsed_questions || 0} question(s).`, 'success', false)
    }, { successMessage: 'Marking scheme processed.' })
  } catch (err) {
    console.error(err)
  }
})

uploadSheetBtn.addEventListener('click', async () => {
  if (!currentExamId) {
    setStatus('Create/load an assessment first.', 'error', false)
    return
  }

  const studentName = document.getElementById('studentName').value.trim()
  const file = document.getElementById('answerSheetInput').files[0]
  if (!studentName || !file) {
    setStatus('Provide student name and answer sheet file.', 'error', false)
    return
  }

  try {
    await runTask('Uploading answer sheet and extracting text...', async () => {
      const form = new FormData()
      form.append('student_name', studentName)
      form.append('file', file)
      const res = await request(`/exams/${currentExamId}/answersheets`, { method: 'POST', body: form })
      document.getElementById('studentName').value = ''
      document.getElementById('answerSheetInput').value = ''
      await loadSheets()
      const conf = res.ocr_confidence ? res.ocr_confidence.toFixed(2) : 'N/A'
      setStatus(`Sheet uploaded. OCR: ${res.ocr_status}, confidence: ${conf}`, 'success', false)
    }, { successMessage: 'Answer sheet processed.' })
  } catch (err) {
    console.error(err)
  }
})

exportExcelBtn.addEventListener('click', async () => {
  if (!currentExamId) {
    setStatus('Create/load an assessment first.', 'error', false)
    return
  }
  try {
    await runTask('Preparing Excel export...', async () => {
      const blobRes = await fetch(`${API}/exams/${currentExamId}/answersheets/export-excel`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!blobRes.ok) {
        let msg = 'Export failed'
        try {
          const data = await blobRes.json()
          msg = data.detail || msg
        } catch (_) {}
        throw new Error(msg)
      }
      const blob = await blobRes.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `exam_${currentExamId}_answersheets.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    }, { successMessage: 'Excel exported successfully.' })
  } catch (err) {
    console.error(err)
  }
})

logoutBtn.addEventListener('click', () => {
  token = ''
  currentExamId = null
  localStorage.removeItem('token')
  setAuthUI()
  resultCard.classList.add('hidden')
  questionsList.className = 'questions-list empty'
  questionsList.textContent = 'No questions parsed yet.'
  setStatus('Logged out.', 'info', false)
})

setAuthUI()
if (token) {
  runTask('Restoring session...', async () => {
    await loadExams()
    await loadExamDetail()
  }, { successMessage: 'Session restored.', blockUI: false }).catch(() => {
    token = ''
    localStorage.removeItem('token')
    setAuthUI()
    setStatus('Session expired. Please login again.', 'error', false)
  })
} else {
  setStatus('Please login to start.', 'info', false)
}
