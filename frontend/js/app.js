/**
 * Mini-RAG 个人知识库前端逻辑
 */

// API 基础地址
const API_BASE = '';

// 当前查看的文档 ID
let currentDocId = null;

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadTags();
    loadDocuments();
});

// ==================== 统计信息 ====================

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
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
        const response = await fetch(`${API_BASE}/api/tags`);
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

async function loadDocuments() {
    try {
        const response = await fetch(`${API_BASE}/api/documents?limit=50`);
        const data = await response.json();
        
        const documentsList = document.getElementById('documentsList');
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
            <div class="doc-card" onclick="viewDocument('${doc.id}')">
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
        showToast('加载文档失败', 'error');
    }
}

async function viewDocument(docId) {
    try {
        const response = await fetch(`${API_BASE}/api/documents/${docId}`);
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
    const title = document.getElementById('viewTitle').textContent;
    const content = document.getElementById('viewContent').textContent;
    const tags = document.getElementById('viewTags').textContent;
    
    hideViewModal();
    
    document.getElementById('docId').value = currentDocId;
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
            response = await fetch(`${API_BASE}/api/documents/${docId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } else {
            response = await fetch(`${API_BASE}/api/documents`, {
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
    if (!currentDocId) return;
    
    if (!confirm('确定要删除这篇文档吗？此操作不可恢复。')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/documents/${currentDocId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            throw new Error('删除失败');
        }
        
        hideViewModal();
        loadDocuments();
        loadTags();
        loadStats();
        showToast('文档删除成功', 'success');
    } catch (error) {
        console.error('删除文档失败:', error);
        showToast('删除文档失败', 'error');
    }
}

function hideViewModal() {
    document.getElementById('viewModal').classList.add('hidden');
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
        const response = await fetch(`${API_BASE}/api/search`, {
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
            <div class="search-result-item" onclick="viewDocument('${result.id}')">
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
    
    if (!question) {
        showToast('请输入问题', 'error');
        return;
    }
    
    const qaAnswer = document.getElementById('qaAnswer');
    const answerContent = document.getElementById('answerContent');
    const sourcesList = document.getElementById('sourcesList');
    
    qaAnswer.classList.remove('hidden');
    answerContent.innerHTML = '<div class="loading"><i class="fas fa-spinner"></i> 正在思考...</div>';
    sourcesList.innerHTML = '';
    
    try {
        const response = await fetch(`${API_BASE}/api/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, context_limit: 3 })
        });
        
        const data = await response.json();
        
        // 显示回答
        answerContent.innerHTML = formatAnswer(data.answer);
        
        // 显示来源
        if (data.sources && data.sources.length > 0) {
            sourcesList.innerHTML = data.sources.map(source => `
                <div class="source-item" onclick="viewDocument('${source.id}')" style="cursor: pointer;">
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
    }
}

function formatAnswer(answer) {
    // 简单的 Markdown 格式化
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
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    
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

function showToast(message, type = '') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.classList.remove('hidden');
    
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}