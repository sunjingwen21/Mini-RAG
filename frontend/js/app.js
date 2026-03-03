/**
 * Mini-RAG 个人知识库前端逻辑
 */

// API 基础地址
const API_BASE = '';
const AUTH_STORAGE_KEY = 'mini_rag_admin_token';

// 当前查看的文档 ID
let currentDocId = null;
let isDeletingDocument = false;
let isAskingQuestion = false;
let documentsLoadSequence = 0;
let authModalResolver = null;
let confirmModalResolver = null;

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', async () => {
    const authenticated = await ensureAuthenticated();
    if (!authenticated) {
        return;
    }

    loadStats();
    loadTags();
    loadDocuments();
});

function getAdminToken() {
    return localStorage.getItem(AUTH_STORAGE_KEY) || '';
}

function setAdminToken(token) {
    localStorage.setItem(AUTH_STORAGE_KEY, token);
}

function clearAdminToken() {
    localStorage.removeItem(AUTH_STORAGE_KEY);
}

function showAuthModal(force = false) {
    const modal = document.getElementById('authModal');
    const message = document.getElementById('authModalMessage');
    const input = document.getElementById('authTokenInput');
    const title = document.getElementById('authModalTitle');
    const currentToken = force ? '' : getAdminToken();

    title.textContent = force ? '访问令牌失效' : '输入访问令牌';
    message.textContent = force ? '访问令牌无效，请重新输入。' : '请输入访问令牌以继续访问知识库。';
    input.value = currentToken;

    modal.classList.remove('hidden');

    setTimeout(() => input.focus(), 0);

    return new Promise(resolve => {
        authModalResolver = resolve;
    });
}

async function ensureAuthenticated(force = false) {
    let token = getAdminToken();
    if (!token || force) {
        token = await showAuthModal(force);
    }
    return Boolean(token);
}

function changeAuthToken() {
    showAuthModal(true).then(token => {
        if (token) {
            showToast('访问令牌已更新', 'success');
        }
    });
}

async function apiFetch(path, options = {}, retry = true) {
    let token = getAdminToken();
    if (!token) {
        const authenticated = await ensureAuthenticated();
        if (!authenticated) {
            throw new Error('未提供访问令牌');
        }
        token = getAdminToken();
    }

    const headers = new Headers(options.headers || {});
    headers.set('X-Admin-Token', token);

    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers
    });

    if (response.status === 401 && retry) {
        clearAdminToken();
        const authenticated = await ensureAuthenticated(true);
        if (authenticated) {
            return apiFetch(path, options, false);
        }
    }

    return response;
}

// ==================== 统计信息 ====================

async function loadStats() {
    try {
        const response = await apiFetch('/api/stats');
        const data = await response.json();

        document.getElementById('totalDocs').textContent = data.total_documents;
        document.getElementById('totalTags').textContent = data.total_tags;
    } catch (error) {
        console.error('加载统计信息失败:', error);
    }
}

// ==================== 标签管理 ====================

async function loadTags() {
    try {
        const response = await apiFetch('/api/tags');
        const tags = await response.json();

        const tagsList = document.getElementById('tagsList');

        if (tags.length === 0) {
            tagsList.innerHTML = '<span class="no-tags" style="color: #94a3b8; font-size: 13px;">暂无标签</span>';
            return;
        }

        tagsList.innerHTML = tags.map(tag => `
            <span class="tag-item" onclick="filterByTag('${tag.name}')">
                ${escapeHtml(tag.name)}
                <span class="tag-count">${tag.count}</span>
            </span>
        `).join('');
    } catch (error) {
        console.error('加载标签失败:', error);
    }
}

function filterByTag(tag) {
    document.getElementById('searchInput').value = tag;
    switchTab('search');
    performSearch();
}

// ==================== 文档管理 ====================

function renderDocumentsErrorState(message = '加载文档失败，请重试') {
    const documentsList = document.getElementById('documentsList');
    documentsList.innerHTML = `
        <div class="empty-state">
            <i class="fas fa-exclamation-circle"></i>
            <p>${escapeHtml(message)}</p>
            <button class="btn-secondary" style="margin-top: 12px;" onclick="loadDocuments()">重试</button>
        </div>
    `;
}

async function loadDocuments(retryCount = 0) {
    const requestId = ++documentsLoadSequence;
    const documentsList = document.getElementById('documentsList');

    if (retryCount === 0) {
        documentsList.innerHTML = `
            <div class="loading">
                <i class="fas fa-spinner"></i>
                <p>正在加载文档...</p>
            </div>
        `;
    }

    try {
        const response = await apiFetch('/api/documents?limit=50');
        if (!response.ok) {
            throw new Error(`加载失败(${response.status})`);
        }
        const data = await response.json();
        const isValidPayload = typeof data.total === 'number' && Array.isArray(data.documents);

        if (!isValidPayload) {
            throw new Error('接口返回格式异常');
        }

        if (requestId !== documentsLoadSequence) {
            console.warn('忽略过期的文档列表响应');
            return;
        }

        if (data.total > 0 && data.documents.length === 0 && retryCount < 1) {
            console.warn('文档总数大于 0，但当前列表为空，自动重试一次', data);
            setTimeout(() => {
                if (requestId === documentsLoadSequence) {
                    loadDocuments(retryCount + 1);
                }
            }, 300);
            return;
        }

        document.getElementById('docCount').textContent = `共 ${data.total} 篇文档`;

        if (data.documents.length === 0) {
            documentsList.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-file-alt"></i>
                    <p>还没有文档，点击"新建文档"开始吧！</p>
                </div>
            `;
            return;
        }

        documentsList.innerHTML = data.documents.map(doc => `
            <div class="doc-card" data-doc-id="${doc.id}" onclick="viewDocument('${doc.id}')">
                <div class="doc-card-title">${escapeHtml(doc.title)}</div>
                <div class="doc-card-preview">${escapeHtml(doc.content.substring(0, 150))}...</div>
                <div class="doc-card-meta">
                    <div class="doc-card-tags">
                        ${doc.tags.slice(0, 3).map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}
                    </div>
                    <span>${formatDate(doc.updated_at)}</span>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('加载文档失败:', error);
        if (requestId !== documentsLoadSequence) {
            return;
        }
        renderDocumentsErrorState('文档列表加载失败，请点击重试');
        showToast('加载文档失败', 'error');
    }
}

async function viewDocument(docId) {
    try {
        const response = await apiFetch(`/api/documents/${docId}`);
        if (!response.ok) {
            throw new Error('加载失败');
        }
        const doc = await response.json();

        currentDocId = docId;

        document.getElementById('viewTitle').textContent = doc.title;
        document.getElementById('viewTime').textContent = formatDate(doc.updated_at);
        document.getElementById('viewTags').textContent = doc.tags.join(', ') || '无标签';
        document.getElementById('viewContent').textContent = doc.content;

        document.getElementById('viewModal').classList.remove('hidden');
    } catch (error) {
        console.error('加载文档详情失败:', error);
        showToast('加载文档详情失败', 'error');
    }
}

// ==================== 文档编辑 ====================

function showDocModal(docId = null) {
    document.getElementById('docId').value = docId || '';
    document.getElementById('docTitle').value = '';
    document.getElementById('docContent').value = '';
    document.getElementById('docTags').value = '';
    document.getElementById('modalTitle').textContent = '新建文档';
    document.getElementById('docModal').classList.remove('hidden');
}

function hideDocModal() {
    document.getElementById('docModal').classList.add('hidden');
}

function editCurrentDoc() {
    const docId = currentDocId;
    const title = document.getElementById('viewTitle').textContent;
    const content = document.getElementById('viewContent').textContent;
    const tags = document.getElementById('viewTags').textContent;

    hideViewModal();

    document.getElementById('docId').value = docId;
    document.getElementById('docTitle').value = title;
    document.getElementById('docContent').value = content;
    document.getElementById('docTags').value = tags === '无标签' ? '' : tags;
    document.getElementById('modalTitle').textContent = '编辑文档';
    document.getElementById('docModal').classList.remove('hidden');
}

async function saveDocument() {
    const docId = document.getElementById('docId').value;
    const title = document.getElementById('docTitle').value.trim();
    const content = document.getElementById('docContent').value.trim();
    const tagsInput = document.getElementById('docTags').value.trim();

    if (!title || !content) {
        showToast('请填写标题和内容', 'error');
        return;
    }

    const tags = tagsInput ? tagsInput.split(',').map(t => t.trim()).filter(t => t) : [];

    const payload = { title, content, tags };

    try {
        let response;
        if (docId) {
            response = await apiFetch(`/api/documents/${docId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } else {
            response = await apiFetch('/api/documents', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        }

        if (!response.ok) {
            throw new Error('保存失败');
        }

        hideDocModal();
        loadDocuments();
        loadTags();
        loadStats();
        showToast(docId ? '文档更新成功' : '文档创建成功', 'success');
    } catch (error) {
        console.error('保存文档失败:', error);
        showToast('保存文档失败', 'error');
    }
}

async function deleteCurrentDoc() {
    if (!currentDocId || isDeletingDocument) return;

    if (!confirm('确定要删除这篇文档吗？此操作不可恢复。')) {
        return;
    }

    const docIdToDelete = currentDocId;
    isDeletingDocument = true;
    hideViewModal();
    removeDocumentFromUI(docIdToDelete);

    try {
        const response = await apiFetch(`/api/documents/${docIdToDelete}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('删除失败');
        }

        loadDocuments();
        loadTags();
        loadStats();
        showToast('文档删除成功', 'success');
    } catch (error) {
        console.error('删除文档失败:', error);
        loadDocuments();
        loadTags();
        loadStats();
        showToast('删除文档失败', 'error');
    } finally {
        isDeletingDocument = false;
    }
}

function hideViewModal() {
    document.getElementById('viewModal').classList.add('hidden');
    currentDocId = null;
    document.getElementById('viewTitle').textContent = '文档详情';
    document.getElementById('viewTime').textContent = '';
    document.getElementById('viewTags').textContent = '';
    document.getElementById('viewContent').textContent = '';
}

function removeDocumentFromUI(docId) {
    document.querySelectorAll(`[data-doc-id="${docId}"]`).forEach(node => node.remove());

    const remainingCards = document.querySelectorAll('.doc-card').length;
    const docCount = document.getElementById('docCount');
    docCount.textContent = `共 ${remainingCards} 篇文档`;

    const totalDocs = document.getElementById('totalDocs');
    const currentTotal = parseInt(totalDocs.textContent, 10);
    if (!Number.isNaN(currentTotal) && currentTotal > 0) {
        totalDocs.textContent = String(currentTotal - 1);
    }

    const documentsList = document.getElementById('documentsList');
    if (remainingCards === 0) {
        documentsList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-file-alt"></i>
                <p>还没有文档，点击"新建文档"开始吧！</p>
            </div>
        `;
    }
}

// ==================== 搜索功能 ====================

function handleSearchKey(event) {
    if (event.key === 'Enter') {
        performSearch();
    }
}

async function performSearch() {
    const query = document.getElementById('searchInput').value.trim();

    if (!query) {
        showToast('请输入搜索内容', 'error');
        return;
    }

    switchTab('search');

    const searchResults = document.getElementById('searchResults');
    searchResults.innerHTML = `
        <div class="loading">
            <i class="fas fa-spinner"></i>
            <p>正在搜索...</p>
        </div>
    `;

    try {
        const response = await apiFetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, limit: 10 })
        });

        const results = await response.json();

        document.getElementById('searchInfo').textContent = `找到 ${results.length} 个相关结果`;

        if (results.length === 0) {
            searchResults.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-search"></i>
                    <p>没有找到相关内容</p>
                </div>
            `;
            return;
        }

        searchResults.innerHTML = results.map(result => `
            <div class="search-result-item" data-doc-id="${result.id}" onclick="viewDocument('${result.id}')">
                <div class="search-result-header">
                    <div class="search-result-title">${escapeHtml(result.title)}</div>
                    <span class="search-result-score">${(result.score * 100).toFixed(1)}%</span>
                </div>
                <div class="search-result-content">${escapeHtml(result.content.substring(0, 300))}...</div>
                <div class="search-result-tags">
                    ${result.tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('搜索失败:', error);
        searchResults.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-circle"></i>
                <p>搜索失败，请稍后重试</p>
            </div>
        `;
    }
}

// ==================== 智能问答 ====================

async function askQuestion() {
    const question = document.getElementById('questionInput').value.trim();
    const askButton = document.getElementById('askQuestionBtn');

    if (!question) {
        showToast('请输入问题', 'error');
        return;
    }

    if (isAskingQuestion) {
        return;
    }

    const qaAnswer = document.getElementById('qaAnswer');
    const answerMeta = document.getElementById('answerMeta');
    const answerContent = document.getElementById('answerContent');
    const sourcesList = document.getElementById('sourcesList');
    const originalButtonHtml = askButton ? askButton.innerHTML : '';

    isAskingQuestion = true;
    if (askButton) {
        askButton.disabled = true;
        askButton.innerHTML = '<i class="fas fa-spinner"></i> 处理中...';
    }

    qaAnswer.classList.remove('hidden');
    answerMeta.classList.add('hidden');
    answerMeta.innerHTML = '';
    answerContent.innerHTML = '<div class="loading"><i class="fas fa-spinner"></i> 正在思考...</div>';
    sourcesList.innerHTML = '';

    try {
        let data = await requestAnswer(question, false);

        if (data.needs_model_confirmation) {
            const shouldContinue = await showConfirmModal(
                '知识库并不包含相关资料，是否调用模型继续询问？',
                '继续提问'
            );

            if (shouldContinue) {
                answerMeta.classList.add('hidden');
                answerMeta.innerHTML = '';
                answerContent.innerHTML = '<div class="loading"><i class="fas fa-spinner"></i> 正在调用模型...</div>';
                data = await requestAnswer(question, true);
            } else {
                answerMeta.classList.add('hidden');
                answerMeta.innerHTML = '';
                answerContent.innerHTML = '<p style="color: var(--text-secondary);">知识库不存在该资料。</p>';
                sourcesList.innerHTML = '<p style="color: var(--text-secondary);">暂无参考来源</p>';
                return;
            }
        }

        renderAnswerMeta(data);

        // 显示回答
        answerContent.innerHTML = formatAnswer(data.answer);

        // 显示来源
        if (data.sources && data.sources.length > 0) {
            sourcesList.innerHTML = data.sources.map(source => `
                <div class="source-item" data-doc-id="${source.id}" onclick="viewDocument('${source.id}')" style="cursor: pointer;">
                    <span class="source-title">${escapeHtml(source.title)}</span>
                    <span class="source-score">相关度: ${(source.score * 100).toFixed(1)}%</span>
                </div>
            `).join('');
        } else {
            sourcesList.innerHTML = '<p style="color: var(--text-secondary);">暂无参考来源</p>';
        }
    } catch (error) {
        console.error('问答失败:', error);
        answerContent.innerHTML = '<p style="color: var(--danger-color);">问答失败，请稍后重试</p>';
    } finally {
        isAskingQuestion = false;
        if (askButton) {
            askButton.disabled = false;
            askButton.innerHTML = originalButtonHtml;
        }
    }
}

function renderAnswerMeta(data) {
    const answerMeta = document.getElementById('answerMeta');
    const messages = [];

    if (data.used_model_fallback) {
        const modelSuffix = data.model_name ? `（模型：${data.model_name}）` : '';
        messages.push(`本次为通用模型回答${modelSuffix}`);
    } else if (data.knowledge_found) {
        messages.push('本次基于知识库回答');
    }

    if (data.answer_truncated) {
        messages.push('回答较长，当前结果可能仍未完整');
    }

    if (messages.length === 0) {
        answerMeta.classList.add('hidden');
        answerMeta.textContent = '';
        return;
    }

    answerMeta.textContent = messages.join('；');
    answerMeta.classList.remove('hidden');
}

async function requestAnswer(question, allowModelFallback = false) {
    const response = await apiFetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            question,
            context_limit: 3,
            allow_model_fallback: allowModelFallback
        })
    });

    if (!response.ok) {
        throw new Error('问答请求失败');
    }

    return response.json();
}

function formatAnswer(answer) {
    if (typeof marked !== 'undefined') {
        return marked.parse(answer);
    }
    // 回退方案
    return answer
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
}

// ==================== 标签页切换 ====================

function switchTab(tab) {
    // 隐藏所有内容区域
    document.getElementById('documentsSection').classList.add('hidden');
    document.getElementById('searchSection').classList.add('hidden');
    document.getElementById('qaSection').classList.add('hidden');

    // 移除所有标签页激活状态
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));

    // 显示选中的内容区域
    switch (tab) {
        case 'documents':
            document.getElementById('documentsSection').classList.remove('hidden');
            document.querySelectorAll('.tab-btn')[0].classList.add('active');
            break;
        case 'search':
            document.getElementById('searchSection').classList.remove('hidden');
            document.querySelectorAll('.tab-btn')[1].classList.add('active');
            break;
        case 'qa':
            document.getElementById('qaSection').classList.remove('hidden');
            document.querySelectorAll('.tab-btn')[2].classList.add('active');
            break;
    }
}

// ==================== 工具函数 ====================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    const date = parseServerDate(dateString);
    const now = new Date();
    const diff = Math.max(0, now - date);

    // 一小时内
    if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        return minutes <= 1 ? '刚刚' : `${minutes} 分钟前`;
    }

    // 一天内
    if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        return `${hours} 小时前`;
    }

    // 一周内
    if (diff < 604800000) {
        const days = Math.floor(diff / 86400000);
        return `${days} 天前`;
    }

    // 其他
    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

function parseServerDate(dateString) {
    if (!dateString) {
        return new Date();
    }

    const hasExplicitTimezone = /(?:Z|[+-]\d{2}:\d{2})$/.test(dateString);
    const normalized = hasExplicitTimezone ? dateString : `${dateString}Z`;
    const parsed = new Date(normalized);

    if (Number.isNaN(parsed.getTime())) {
        return new Date(dateString);
    }

    return parsed;
}

function showToast(message, type = '') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.classList.remove('hidden');

    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}

// ==================== 模型设置 ====================

const MODEL_PRESETS = {
    'deepseek': {
        url: 'https://api.deepseek.com/v1',
        model: 'deepseek-chat'
    },
    'glm': {
        url: 'https://open.bigmodel.cn/api/paas/v4',
        model: 'glm-4'
    },
    'qwen': {
        url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        model: 'qwen-turbo'
    },
    'minimax': {
        url: 'https://api.minimax.chat/v1',
        model: 'abab6.5-chat'
    },
    'custom': {
        url: '',
        model: ''
    }
};

async function showSettingsModal() {
    document.getElementById('settingsModal').classList.remove('hidden');
    // 获取当前配置
    try {
        const response = await apiFetch('/api/settings');
        const settings = await response.json();

        document.getElementById('settingBaseUrl').value = settings.llm_base_url || '';
        document.getElementById('settingApiKey').value = settings.llm_api_key || '';
        document.getElementById('settingModelName').value = settings.llm_model || '';

        // 移除所有预设的激活状态
        document.querySelectorAll('.btn-preset').forEach(btn => btn.classList.remove('active'));
    } catch (error) {
        console.error('加载设置失败:', error);
    }
}

function hideSettingsModal() {
    document.getElementById('settingsModal').classList.add('hidden');
}

function applyPreset(presetName) {
    const preset = MODEL_PRESETS[presetName];
    if (preset) {
        document.getElementById('settingBaseUrl').value = preset.url;
        document.getElementById('settingModelName').value = preset.model;

        // 更新按钮样式
        document.querySelectorAll('.btn-preset').forEach(btn => btn.classList.remove('active'));
        if (typeof window !== 'undefined' && window.event && window.event.target) {
            window.event.target.classList.add('active');
        }
    }
}

async function saveSettings() {
    const baseUrl = document.getElementById('settingBaseUrl').value.trim();
    const apiKey = document.getElementById('settingApiKey').value.trim();
    const modelName = document.getElementById('settingModelName').value.trim();

    // 显示保存中...
    const saveBtn = document.querySelector('#settingsModal .btn-primary');
    const originalText = saveBtn.textContent;
    saveBtn.textContent = '保存中...';
    saveBtn.disabled = true;

    try {
        const response = await apiFetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                llm_base_url: baseUrl,
                llm_api_key: apiKey,
                llm_model: modelName
            })
        });

        if (!response.ok) throw new Error('保存失败');

        hideSettingsModal();
        showToast('大模型配置保存成功，即刻生效！', 'success');
    } catch (error) {
        console.error('保存设置失败:', error);
        showToast('保存配置失败，请检查网络重试', 'error');
    } finally {
        saveBtn.textContent = originalText;
        saveBtn.disabled = false;
    }
}

function submitAuthModal() {
    const input = document.getElementById('authTokenInput');
    const token = input.value.trim();

    if (!token) {
        clearAdminToken();
        if (authModalResolver) {
            const resolve = authModalResolver;
            authModalResolver = null;
            hideAuthModal();
            resolve('');
        }
        return;
    }

    setAdminToken(token);
    if (authModalResolver) {
        const resolve = authModalResolver;
        authModalResolver = null;
        hideAuthModal();
        resolve(token);
    }
}

function cancelAuthModal() {
    if (authModalResolver) {
        const resolve = authModalResolver;
        authModalResolver = null;
        hideAuthModal();
        resolve('');
    }
}

function hideAuthModal() {
    document.getElementById('authModal').classList.add('hidden');
}

function handleAuthTokenKey(event) {
    if (event.key === 'Enter') {
        submitAuthModal();
    }
}

function showConfirmModal(message, title = '确认操作') {
    document.getElementById('confirmModalTitle').textContent = title;
    document.getElementById('confirmModalMessage').textContent = message;
    document.getElementById('confirmModal').classList.remove('hidden');

    return new Promise(resolve => {
        confirmModalResolver = resolve;
    });
}

function resolveConfirmModal(result) {
    if (confirmModalResolver) {
        const resolve = confirmModalResolver;
        confirmModalResolver = null;
        document.getElementById('confirmModal').classList.add('hidden');
        resolve(result);
    }
}
